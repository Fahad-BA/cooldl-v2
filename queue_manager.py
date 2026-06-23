"""
Advanced Rate Limiting & Queue Management System for CoolDL Phase 2
Provides smart queue prioritization, predictive rate limiting, wait time
estimation, priority access for trusted users, and fair usage alerts.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import IntEnum

import db
from config import settings

logger = logging.getLogger(__name__)


class UserTier(IntEnum):
    """User trust tiers for priority assignment."""
    BLOCKED = 0
    NEW = 1
    REGULAR = 2
    TRUSTED = 3
    VIP = 4


class QueuePriority(IntEnum):
    """Download queue priority levels (higher = processed first)."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class QueuedDownload:
    """Represents a queued download request."""
    chat_id: int
    url: str
    normalized_url: str
    user_id: int
    name: str
    username: str
    source: str
    priority: QueuePriority
    user_tier: UserTier
    enqueued_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_size_mb: Optional[float] = None
    estimated_duration_s: int = 60
    status: str = 'queued'  # queued, processing, completed, failed, cancelled
    attempts: int = 0
    max_attempts: int = 3
    
    @property
    def wait_time(self) -> float:
        """Time spent waiting in queue (seconds)."""
        return (datetime.now() - self.enqueued_at).total_seconds()
    
    @property
    def is_expired(self) -> bool:
        """Check if queued item has expired (5 min max wait)."""
        return self.wait_time > 300 and self.status == 'queued'


@dataclass
class UserBehaviorProfile:
    """Tracks user behavior patterns for predictive rate limiting."""
    chat_id: int
    tier: UserTier = UserTier.NEW
    # Download history timestamps
    download_times: deque = field(default_factory=lambda: deque(maxlen=200))
    # Failure history
    failure_times: deque = field(default_factory=lambda: deque(maxlen=50))
    # Download durations (for estimation)
    download_durations: deque = field(default_factory=lambda: deque(maxlen=20))
    # Size history
    download_sizes: deque = field(default_factory=lambda: deque(maxlen=20))
    # Time between requests (for pattern detection)
    request_intervals: deque = field(default_factory=lambda: deque(maxlen=30))
    last_request_time: Optional[datetime] = None
    # Trust score (0-100)
    trust_score: int = 50
    # Abuse indicators
    abuse_flags: int = 0
    last_abuse_check: Optional[datetime] = None
    
    @property
    def total_downloads(self) -> int:
        return len(self.download_times)
    
    @property
    def recent_downloads_1h(self) -> int:
        """Downloads in the last hour."""
        now = datetime.now()
        return sum(1 for t in self.download_times if (now - t).total_seconds() < 3600)
    
    @property
    def recent_downloads_24h(self) -> int:
        """Downloads in the last 24 hours."""
        now = datetime.now()
        return sum(1 for t in self.download_times if (now - t).total_seconds() < 86400)
    
    @property
    def recent_failures_1h(self) -> int:
        """Failures in the last hour."""
        now = datetime.now()
        return sum(1 for t in self.failure_times if (now - t).total_seconds() < 3600)
    
    @property
    def failure_rate(self) -> float:
        """Recent failure rate (0-1)."""
        total = len(self.download_times) + len(self.failure_times)
        if total == 0:
            return 0.0
        return len(self.failure_times) / total
    
    @property
    def avg_download_duration(self) -> float:
        """Average download duration in seconds."""
        if not self.download_durations:
            return 60.0  # Default estimate
        return sum(self.download_durations) / len(self.download_durations)
    
    @property
    def avg_download_size_mb(self) -> float:
        """Average download size in MB."""
        if not self.download_sizes:
            return 50.0  # Default estimate
        return sum(self.download_sizes) / len(self.download_sizes)
    
    @property
    def avg_request_interval(self) -> float:
        """Average time between requests (seconds)."""
        if len(self.request_intervals) < 2:
            return 3600.0  # Default: 1 hour
        return sum(self.request_intervals) / len(self.request_intervals)


class QueueManager:
    """
    Advanced queue management with intelligent prioritization.
    
    Features:
    - Smart queue prioritization based on user history and behavior
    - Predictive rate limiting using user behavior analysis
    - Wait time estimation for queued downloads
    - Priority access for trusted/VIP users
    - Fair usage alerts with actionable suggestions
    """
    
    # Tier thresholds (based on download count and trust score)
    TIER_THRESHOLDS = {
        UserTier.NEW: {'min_downloads': 0, 'min_trust': 0},
        UserTier.REGULAR: {'min_downloads': 10, 'min_trust': 50},
        UserTier.TRUSTED: {'min_downloads': 50, 'min_trust': 75},
        UserTier.VIP: {'min_downloads': 100, 'min_trust': 90},
    }
    
    # Tier benefits
    TIER_BENEFITS = {
        UserTier.NEW: {
            'hourly_limit': settings.rate_limit.max_downloads_per_hour,
            'priority': QueuePriority.NORMAL,
            'concurrent_limit': 1,
            'description': 'New user'
        },
        UserTier.REGULAR: {
            'hourly_limit': settings.rate_limit.max_downloads_per_hour + 2,
            'priority': QueuePriority.NORMAL,
            'concurrent_limit': 1,
            'description': 'Regular user'
        },
        UserTier.TRUSTED: {
            'hourly_limit': settings.rate_limit.max_downloads_per_hour + 5,
            'priority': QueuePriority.HIGH,
            'concurrent_limit': 2,
            'description': 'Trusted user (+5 downloads/hr)'
        },
        UserTier.VIP: {
            'hourly_limit': settings.rate_limit.max_downloads_per_hour + 10,
            'priority': QueuePriority.URGENT,
            'concurrent_limit': 3,
            'description': 'VIP user (+10 downloads/hr, priority queue)'
        },
    }
    
    # Trust score adjustments
    TRUST_ADJUSTMENTS = {
        'successful_download': 2,
        'failed_download': -1,
        'rapid_request': -5,
        'abuse_detected': -20,
        'long_term_user': 10,  # Bonus for 30+ day accounts
        'consistent_usage': 5,  # Regular usage pattern
    }
    
    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._queue_items: Dict[str, QueuedDownload] = {}  # queue_id -> item
        self._user_profiles: Dict[int, UserBehaviorProfile] = {}
        self._processing: Dict[int, QueuedDownload] = {}  # chat_id -> currently processing
        self._active_counts: Dict[int, int] = defaultdict(int)  # chat_id -> active count
        self._max_concurrent = settings.rate_limit.max_concurrent
        self._total_processed = 0
        self._total_queued = 0
        self._initialized = False
    
    async def initialize(self):
        """Initialize the queue manager (call once at startup)."""
        if self._initialized:
            return
        
        logger.info("Initializing Queue Manager...")
        
        # Load user profiles from database
        await self._load_user_profiles()
        
        self._initialized = True
        logger.info(
            f"Queue Manager initialized: {len(self._user_profiles)} user profiles loaded"
        )
    
    async def _load_user_profiles(self):
        """Load user behavior profiles from database history."""
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            
            # Get download history per user
            cur.execute("""
                SELECT chat_id, 
                       COUNT(*) as total_downloads,
                       MIN(timestamp) as first_download,
                       MAX(timestamp) as last_download,
                       SUM(CASE WHEN file_size > 0 THEN 1 ELSE 0 END) as successful,
                       AVG(file_size) as avg_size
                FROM downloads 
                GROUP BY chat_id
            """)
            
            for row in cur.fetchall():
                chat_id = row['chat_id']
                profile = UserBehaviorProfile(chat_id=chat_id)
                
                # Set download count
                total = row['total_downloads'] or 0
                for _ in range(min(total, 200)):
                    profile.download_times.append(datetime.min)
                
                # Calculate trust score based on history
                trust = 50  # Start at baseline
                trust += min(total * 2, 30)  # Up to +30 for downloads
                
                # First download time (account age)
                first_dl = row['first_download']
                if first_dl:
                    try:
                        first_dt = datetime.fromisoformat(first_dl.replace('Z', '+00:00'))
                        account_age_days = (datetime.now() - first_dt).days
                        if account_age_days > 30:
                            trust += self.TRUST_ADJUSTMENTS['long_term_user']
                    except (ValueError, TypeError):
                        pass
                
                profile.trust_score = min(100, max(0, trust))
                profile.tier = self._calculate_tier(total, profile.trust_score)
                
                # Set avg size
                if row['avg_size']:
                    profile.download_sizes.append(row['avg_size'] / (1024 * 1024))
                
                self._user_profiles[chat_id] = profile
            
            conn.close()
            logger.info(f"Loaded {len(self._user_profiles)} user profiles from database")
            
        except Exception as e:
            logger.error(f"Error loading user profiles: {e}")
    
    def _calculate_tier(self, total_downloads: int, trust_score: int) -> UserTier:
        """Calculate user tier based on downloads and trust score."""
        # Check from highest tier down
        for tier in [UserTier.VIP, UserTier.TRUSTED, UserTier.REGULAR]:
            threshold = self.TIER_THRESHOLDS[tier]
            if (total_downloads >= threshold['min_downloads'] and 
                trust_score >= threshold['min_trust']):
                return tier
        
        return UserTier.NEW
    
    def get_user_profile(self, chat_id: int) -> UserBehaviorProfile:
        """Get or create user behavior profile."""
        if chat_id not in self._user_profiles:
            self._user_profiles[chat_id] = UserBehaviorProfile(chat_id=chat_id)
        return self._user_profiles[chat_id]
    
    def get_user_tier(self, chat_id: int) -> UserTier:
        """Get user's current tier."""
        profile = self.get_user_profile(chat_id)
        return profile.tier
    
    def update_trust_score(self, chat_id: int, event: str, value: int = 0):
        """
        Update user's trust score based on an event.
        
        Args:
            chat_id: User's chat ID
            event: Event type (successful_download, failed_download, etc.)
            value: Optional custom value
        """
        profile = self.get_user_profile(chat_id)
        
        adjustment = value if value else self.TRUST_ADJUSTMENTS.get(event, 0)
        profile.trust_score = min(100, max(0, profile.trust_score + adjustment))
        
        # Recalculate tier
        old_tier = profile.tier
        profile.tier = self._calculate_tier(profile.total_downloads, profile.trust_score)
        
        if old_tier != profile.tier:
            if profile.tier > old_tier:
                logger.info(
                    f"User {chat_id} promoted: {old_tier.name} → {profile.tier.name} "
                    f"(trust: {profile.trust_score})"
                )
            else:
                logger.info(
                    f"User {chat_id} demoted: {old_tier.name} → {profile.tier.name} "
                    f"(trust: {profile.trust_score})"
                )
    
    def record_download_start(self, chat_id: int):
        """Record that a download has started."""
        profile = self.get_user_profile(chat_id)
        now = datetime.now()
        
        # Track request interval
        if profile.last_request_time:
            interval = (now - profile.last_request_time).total_seconds()
            profile.request_intervals.append(interval)
            
            # Check for rapid requests
            if interval < 5:
                profile.abuse_flags += 1
                self.update_trust_score(chat_id, 'rapid_request')
        
        profile.last_request_time = now
        profile.download_times.append(now)
        self._active_counts[chat_id] += 1
    
    def record_download_complete(self, chat_id: int, success: bool, 
                                  duration_s: float = 0, size_mb: float = 0):
        """Record download completion."""
        profile = self.get_user_profile(chat_id)
        self._active_counts[chat_id] = max(0, self._active_counts[chat_id] - 1)
        
        if success:
            self.update_trust_score(chat_id, 'successful_download')
            if duration_s > 0:
                profile.download_durations.append(duration_s)
            if size_mb > 0:
                profile.download_sizes.append(size_mb)
        else:
            profile.failure_times.append(datetime.now())
            self.update_trust_score(chat_id, 'failed_download')
    
    def check_rate_limit(self, chat_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Intelligent rate limit check based on user tier and behavior.
        
        Returns:
            Tuple of (allowed, message, details_dict)
        """
        profile = self.get_user_profile(chat_id)
        tier = profile.tier
        benefits = self.TIER_BENEFITS.get(tier, self.TIER_BENEFITS[UserTier.NEW])
        hourly_limit = benefits['hourly_limit']
        
        recent = profile.recent_downloads_1h
        details = {
            'tier': tier.name,
            'tier_description': benefits['description'],
            'hourly_limit': hourly_limit,
            'recent_downloads_1h': recent,
            'trust_score': profile.trust_score,
            'concurrent_active': self._active_counts.get(chat_id, 0),
            'concurrent_limit': benefits['concurrent_limit'],
        }
        
        # Check hourly limit
        if recent >= hourly_limit:
            # Calculate time until oldest download in window expires
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            valid_times = [t for t in profile.download_times if t > one_hour_ago]
            
            if valid_times:
                oldest = min(valid_times)
                reset_in = int((oldest + timedelta(hours=1) - now).total_seconds())
                reset_in_min = max(1, reset_in // 60)
            else:
                reset_in_min = 60
            
            details['reset_in_minutes'] = reset_in_min
            
            return False, (
                f"⏱️ You've reached your hourly limit ({recent}/{hourly_limit}). "
                f"Resets in ~{reset_in_min} minutes."
            ), details
        
        # Check concurrent limit
        if self._active_counts.get(chat_id, 0) >= benefits['concurrent_limit']:
            return False, (
                f"⏳ You already have {self._active_counts[chat_id]} download(s) in progress. "
                f"Your tier allows {benefits['concurrent_limit']} concurrent download(s)."
            ), details
        
        # Check for suspicious patterns
        if profile.recent_failures_1h >= 5:
            profile.abuse_flags += 1
            return False, (
                f"⚠️ Too many recent failures ({profile.recent_failures_1h} in the last hour). "
                f"Please wait a bit before trying again."
            ), details
        
        # Check trust score
        if profile.trust_score < 20:
            return False, (
                f"🚫 Your trust score is too low ({profile.trust_score}/100). "
                f"Please contact admin if you believe this is an error."
            ), details
        
        return True, "Rate limit check passed", details
    
    def get_queue_position(self, chat_id: int) -> Optional[int]:
        """Get user's position in the queue (1-based). None if not queued."""
        items = sorted(
            [item for item in self._queue_items.values() if item.status == 'queued'],
            key=lambda x: (-x.priority.value, x.enqueued_at)
        )
        for i, item in enumerate(items, 1):
            if item.chat_id == chat_id:
                return i
        return None
    
    def estimate_wait_time(self, chat_id: int, queue_position: int = None) -> int:
        """
        Estimate wait time for a queued download.
        
        Returns:
            Estimated wait time in seconds
        """
        if queue_position is None:
            queue_position = self.get_queue_position(chat_id)
        
        if queue_position is None or queue_position == 0:
            return 0
        
        # Get active download count
        active = len(self._processing)
        available_slots = max(0, self._max_concurrent - active)
        
        if available_slots > 0 and queue_position == 1:
            return 0  # Will be processed immediately
        
        # Calculate based on average download duration
        # Use global average if no user data
        avg_duration = 60  # Default 60 seconds
        
        # Get average from active downloads or user profile
        profile = self.get_user_profile(chat_id)
        if profile.download_durations:
            avg_duration = profile.avg_download_duration
        
        # Items ahead in queue that need to be processed first
        items_ahead = max(0, queue_position - available_slots)
        wait_time = items_ahead * (avg_duration / max(1, self._max_concurrent))
        
        return int(wait_time)
    
    def get_fair_usage_alert(self, chat_id: int) -> Optional[str]:
        """
        Generate fair usage alert with suggestions.
        
        Returns:
            Alert message if user should be alerted, None otherwise
        """
        profile = self.get_user_profile(chat_id)
        tier = profile.tier
        benefits = self.TIER_BENEFITS.get(tier, self.TIER_BENEFITS[UserTier.NEW])
        hourly_limit = benefits['hourly_limit']
        recent = profile.recent_downloads_1h
        
        # Alert at 80% usage
        if recent >= int(hourly_limit * 0.8) and recent < hourly_limit:
            remaining = hourly_limit - recent
            return (
                f"📊 **Fair Usage Notice**\n\n"
                f"You've used {recent}/{hourly_limit} of your hourly downloads.\n"
                f"Remaining: {remaining}\n\n"
                f"💡 **Tip:** Your tier ({tier.name}) gives you {hourly_limit} downloads/hour. "
                f"Use /stats to see your full statistics."
            )
        
        # Alert for high failure rate
        if profile.failure_rate > 0.3 and profile.total_downloads > 10:
            return (
                f"⚠️ **High Failure Rate**\n\n"
                f"Your recent failure rate is {profile.failure_rate*100:.0f}%.\n"
                f"This could be due to:\n"
                f"• Invalid or expired links\n"
                f"• Server-side issues\n"
                f"• Network problems\n\n"
                f"💡 Try sending fresh URLs."
            )
        
        return None
    
    def get_user_stats(self, chat_id: int) -> Dict[str, Any]:
        """Get comprehensive stats for queue/rate limit display."""
        profile = self.get_user_profile(chat_id)
        tier = profile.tier
        benefits = self.TIER_BENEFITS.get(tier, self.TIER_BENEFITS[UserTier.NEW])
        
        queue_pos = self.get_queue_position(chat_id)
        est_wait = self.estimate_wait_time(chat_id, queue_pos)
        
        return {
            'tier': tier.name,
            'tier_description': benefits['description'],
            'trust_score': profile.trust_score,
            'total_downloads': profile.total_downloads,
            'recent_1h': profile.recent_downloads_1h,
            'recent_24h': profile.recent_downloads_24h,
            'hourly_limit': benefits['hourly_limit'],
            'concurrent_limit': benefits['concurrent_limit'],
            'concurrent_active': self._active_counts.get(chat_id, 0),
            'failure_rate': profile.failure_rate,
            'queue_position': queue_pos,
            'estimated_wait_s': est_wait,
            'avg_download_duration': profile.avg_download_duration,
            'avg_download_size_mb': profile.avg_download_size_mb,
            'abuse_flags': profile.abuse_flags,
        }
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get overall queue statistics."""
        queued_items = [i for i in self._queue_items.values() if i.status == 'queued']
        
        return {
            'total_queued': len(queued_items),
            'total_processing': len(self._processing),
            'total_processed': self._total_processed,
            'available_slots': max(0, self._max_concurrent - len(self._processing)),
            'max_concurrent': self._max_concurrent,
            'active_users': len([1 for c in self._active_counts.values() if c > 0]),
            'total_profiles_tracked': len(self._user_profiles),
        }
    
    async def enqueue_download(self, chat_id: int, url: str, normalized_url: str,
                               user_id: int, name: str, username: str, 
                               source: str, estimated_size_mb: float = None) -> QueuedDownload:
        """
        Add a download to the queue.
        
        The queue uses priority based on user tier, with higher tiers
        getting processed first.
        """
        profile = self.get_user_profile(chat_id)
        tier = profile.tier
        benefits = self.TIER_BENEFITS.get(tier, self.TIER_BENEFITS[UserTier.NEW])
        priority = benefits['priority']
        
        # Estimate duration
        est_duration = int(profile.avg_download_duration)
        
        item = QueuedDownload(
            chat_id=chat_id,
            url=url,
            normalized_url=normalized_url,
            user_id=user_id,
            name=name,
            username=username,
            source=source,
            priority=priority,
            user_tier=tier,
            estimated_size_mb=estimated_size_mb,
            estimated_duration_s=est_duration,
        )
        
        # Generate unique queue ID
        queue_id = f"{chat_id}_{int(time.time())}_{url[:20]}"
        self._queue_items[queue_id] = item
        self._total_queued += 1
        
        logger.info(
            f"Download enqueued: user={chat_id}, tier={tier.name}, "
            f"priority={priority.name}, source={source}"
        )
        
        return item
    
    def dequeue_download(self, queue_id: str) -> Optional[QueuedDownload]:
        """Remove and return a download from the queue."""
        if queue_id in self._queue_items:
            item = self._queue_items.pop(queue_id)
            return item
        return None
    
    def cancel_queued_download(self, chat_id: int) -> bool:
        """Cancel a user's queued download."""
        for qid, item in list(self._queue_items.items()):
            if item.chat_id == chat_id and item.status == 'queued':
                item.status = 'cancelled'
                del self._queue_items[qid]
                logger.info(f"Download cancelled: user={chat_id}, url={item.url[:50]}")
                return True
        return False
    
    def cleanup_expired(self) -> int:
        """Remove expired queue items. Returns count of removed items."""
        expired = []
        for qid, item in list(self._queue_items.items()):
            if item.is_expired:
                item.status = 'expired'
                expired.append(qid)
        
        for qid in expired:
            del self._queue_items[qid]
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired queue items")
        
        return len(expired)
    
    def promote_user(self, chat_id: int, tier: UserTier):
        """Manually set a user's tier (admin action)."""
        profile = self.get_user_profile(chat_id)
        old_tier = profile.tier
        profile.tier = tier
        
        # Adjust trust score to match tier
        threshold = self.TIER_THRESHOLDS.get(tier, {})
        min_trust = threshold.get('min_trust', 50)
        if profile.trust_score < min_trust:
            profile.trust_score = min_trust
        
        logger.info(
            f"User {chat_id} manually set to {tier.name} "
            f"(was {old_tier.name})"
        )
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by download count."""
        sorted_profiles = sorted(
            self._user_profiles.values(),
            key=lambda p: p.total_downloads,
            reverse=True
        )[:limit]
        
        return [
            {
                'chat_id': p.chat_id,
                'total_downloads': p.total_downloads,
                'tier': p.tier.name,
                'trust_score': p.trust_score,
                'recent_24h': p.recent_downloads_24h,
            }
            for p in sorted_profiles
        ]


# Global instance for easy access
queue_manager = QueueManager()


async def initialize_queue_manager():
    """Initialize the global queue manager. Call at startup."""
    await queue_manager.initialize()


def get_rate_limit_info(chat_id: int) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Convenience function for rate limit checking.
    
    Returns:
        Tuple of (allowed, message, details)
    """
    return queue_manager.check_rate_limit(chat_id)


def format_user_stats(chat_id: int) -> str:
    """Format user queue/rate-limit stats as a readable message."""
    stats = queue_manager.get_user_stats(chat_id)
    
    tier_emoji = {
        'NEW': '🆕',
        'REGULAR': '👤',
        'TRUSTED': '⭐',
        'VIP': '👑',
    }.get(stats['tier'], '👤')
    
    lines = [
        f"{tier_emoji} **Your Account Status**\n",
        f"📊 **Tier:** {stats['tier']} - {stats.get('tier_description', '')}",
        f"⭐ **Trust Score:** {stats['trust_score']}/100",
        f"📥 **Total Downloads:** {stats['total_downloads']}",
        f"⚡ **Hourly Usage:** {stats['recent_1h']}/{stats['hourly_limit']}",
        f"📅 **24h Activity:** {stats['recent_24h']} downloads",
        f"🔄 **Concurrent:** {stats['concurrent_active']}/{stats['concurrent_limit']}",
    ]
    
    if stats['queue_position']:
        wait_min = stats['estimated_wait_s'] // 60
        lines.append(f"\n📋 **Queue Position:** #{stats['queue_position']}")
        if stats['estimated_wait_s'] > 0:
            lines.append(f"⏱️ **Estimated Wait:** ~{wait_min}m {stats['estimated_wait_s'] % 60}s")
    
    if stats['failure_rate'] > 0.2:
        lines.append(f"\n⚠️ **Note:** Your failure rate is {stats['failure_rate']*100:.0f}%")
    
    return "\n".join(lines)
