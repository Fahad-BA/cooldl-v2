"""
Advanced Security Management System for CoolDL
Provides intelligent user activity monitoring, suspicious pattern detection, and enhanced security controls.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re
import ipaddress

from config import settings
import db
from blocks import block_user

logger = logging.getLogger(__name__)


class SecurityManager:
    """Advanced security management with intelligent threat detection."""
    
    def __init__(self):
        # Suspicious patterns and thresholds
        self.suspicious_patterns = {
            'rapid_downloads': {
                'threshold': 10,  # downloads in
                'time_window': 60,  # seconds
                'action': 'temp_block'
            },
            'rapid_failures': {
                'threshold': 5,  # failed downloads
                'time_window': 300,  # 5 minutes
                'action': 'warn'
            },
            'url_spam': {
                'threshold': 15,  # URLs in single message
                'action': 'warn'
            },
            'size_abuse': {
                'threshold': 3,  # large files
                'time_window': 3600,  # 1 hour
                'action': 'limit'
            },
            'concurrent_downloads': {
                'threshold': 5,  # simultaneous downloads
                'action': 'queue'
            }
        }
        
        # Malicious URL patterns
        self.malicious_url_patterns = [
            r'malware',
            r'virus.*download',
            r'trojan',
            r'phishing',
            r'scam.*download',
            r'keylogger',
            r'backdoor',
            r'exploit.*download',
            r'suspicious.*link'
        ]
        
        # Bot detection patterns
        self.bot_patterns = [
            r'http://127\.0\.0\.1',
            r'localhost',
            r'bot.*download',
            r'auto.*download',
            r'scraper.*download'
        ]
        
        # Rate limiting data
        self.user_activity = defaultdict(lambda: {
            'downloads': deque(maxlen=100),
            'failures': deque(maxlen=50),
            'urls_count': deque(maxlen=20),
            'large_files': deque(maxlen=10),
            'concurrent': set(),
            'ip_addresses': set(),
            'user_agents': set(),
            'blocked_until': None,
            'warnings': 0,
            'risk_score': 0
        })
        
        # Security thresholds
        self.security_thresholds = {
            'max_warnings': 3,
            'temp_block_duration': 3600,  # 1 hour
            'high_risk_score': 100,
            'medium_risk_score': 50,
            'max_concurrent_downloads': 3,
            'max_urls_per_message': 10
        }
        
        # Initialize security database
        self.initialize_security_db()
    
    def initialize_security_db(self):
        """Initialize security-related database tables."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Security events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    event_type TEXT,
                    details TEXT,
                    risk_score INTEGER,
                    timestamp TIMESTAMP,
                    action_taken TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            
            # User risk scores table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_risk_scores (
                    chat_id INTEGER PRIMARY KEY,
                    risk_score INTEGER DEFAULT 0,
                    threat_level TEXT DEFAULT 'low',
                    last_updated TIMESTAMP,
                    warnings_count INTEGER DEFAULT 0,
                    blocks_count INTEGER DEFAULT 0
                )
            """)
            
            # Security rules table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS security_rules (
                    rule_name TEXT PRIMARY KEY,
                    pattern TEXT,
                    threshold_value INTEGER,
                    time_window INTEGER,
                    action TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    description TEXT
                )
            """)
            
            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_security_events_chat_id ON security_events(chat_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_security_events_timestamp ON security_events(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_risk_scores_score ON user_risk_scores(risk_score)")
            
            conn.commit()
            logger.info("Security database initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize security database: {e}")
        finally:
            conn.close()
    
    def detect_suspicious_patterns(self, chat_id: int, activity_type: str, **kwargs) -> Dict[str, Any]:
        """
        Detect suspicious activity patterns and return threat assessment.
        
        Args:
            chat_id: User's chat ID
            activity_type: Type of activity (download, failure, etc.)
            **kwargs: Additional data for the activity
            
        Returns:
            Dict with threat assessment and recommended action
        """
        user_data = self.user_activity[chat_id]
        current_time = datetime.now()
        threats = []
        risk_score = 0
        recommended_action = 'allow'
        
        # Record the activity
        if activity_type == 'download':
            user_data['downloads'].append(current_time)
            url = kwargs.get('url', '')
            file_size = kwargs.get('file_size', 0)
            
            # Check for URL spam
            urls_in_message = len(re.findall(r'https?://[^\s]+', url))
            if urls_in_message > self.security_thresholds['max_urls_per_message']:
                threats.append({
                    'type': 'url_spam',
                    'severity': 'medium',
                    'description': f'Too many URLs in message: {urls_in_message}'
                })
                risk_score += 25
            
            # Check for large file abuse
            if file_size > 100 * 1024 * 1024:  # Files larger than 100MB
                user_data['large_files'].append(current_time)
                recent_large_files = [
                    t for t in user_data['large_files'] 
                    if (current_time - t).total_seconds() < 3600
                ]
                
                if len(recent_large_files) > self.suspicious_patterns['size_abuse']['threshold']:
                    threats.append({
                        'type': 'size_abuse',
                        'severity': 'medium',
                        'description': f'Too many large file downloads: {len(recent_large_files)}'
                    })
                    risk_score += 30
        
        elif activity_type == 'failure':
            user_data['failures'].append(current_time)
            
            # Check for rapid failures
            recent_failures = [
                t for t in user_data['failures']
                if (current_time - t).total_seconds() < self.suspicious_patterns['rapid_failures']['time_window']
            ]
            
            if len(recent_failures) > self.suspicious_patterns['rapid_failures']['threshold']:
                threats.append({
                    'type': 'rapid_failures',
                    'severity': 'medium',
                    'description': f'Too many failed downloads: {len(recent_failures)}'
                })
                risk_score += 20
        
        # Check for rapid downloads
        recent_downloads = [
            t for t in user_data['downloads']
            if (current_time - t).total_seconds() < self.suspicious_patterns['rapid_downloads']['time_window']
        ]
        
        if len(recent_downloads) > self.suspicious_patterns['rapid_downloads']['threshold']:
            threats.append({
                'type': 'rapid_downloads',
                'severity': 'high',
                'description': f'Too many rapid downloads: {len(recent_downloads)}'
            })
            risk_score += 40
        
        # Check concurrent downloads
        active_downloads = len(user_data['concurrent'])
        if active_downloads > self.security_thresholds['max_concurrent_downloads']:
            threats.append({
                'type': 'concurrent_downloads',
                'severity': 'medium',
                'description': f'Too many concurrent downloads: {active_downloads}'
            })
            risk_score += 15
            recommended_action = 'queue'
        
        # Determine threat level and action
        threat_level = 'low'
        if risk_score >= self.security_thresholds['high_risk_score']:
            threat_level = 'high'
            recommended_action = 'block'
        elif risk_score >= self.security_thresholds['medium_risk_score']:
            threat_level = 'medium'
            if recommended_action == 'allow':
                recommended_action = 'warn'
        
        # Update user risk score
        self.update_user_risk_score(chat_id, risk_score, threat_level)
        
        return {
            'threats_detected': threats,
            'risk_score': risk_score,
            'threat_level': threat_level,
            'recommended_action': recommended_action,
            'timestamp': current_time
        }
    
    def validate_url_safety(self, url: str) -> Tuple[bool, str, int]:
        """
        Validate URL safety and check for malicious content.
        
        Returns:
            Tuple of (is_safe, reason, risk_score)
        """
        url_lower = url.lower()
        risk_score = 0
        reasons = []
        
        # Check for malicious patterns
        for pattern in self.malicious_url_patterns:
            if re.search(pattern, url_lower, re.IGNORECASE):
                reasons.append(f"Malicious pattern detected: {pattern}")
                risk_score += 100
        
        # Check for bot patterns
        for pattern in self.bot_patterns:
            if re.search(pattern, url_lower, re.IGNORECASE):
                reasons.append(f"Bot pattern detected: {pattern}")
                risk_score += 50
        
        # Check for suspicious TLDs
        suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq']
        for tld in suspicious_tlds:
            if url_lower.endswith(tld):
                reasons.append(f"Suspicious TLD: {tld}")
                risk_score += 25
        
        # Check URL length
        if len(url) > 2000:
            reasons.append("URL too long")
            risk_score += 15
        
        # Check for excessive parameters
        param_count = url.count('&') + url.count('?')
        if param_count > 20:
            reasons.append("Excessive URL parameters")
            risk_score += 10
        
        # Determine if URL is safe
        is_safe = risk_score < 50
        
        reason = "; ".join(reasons) if reasons else "URL appears safe"
        
        return is_safe, reason, risk_score
    
    def check_ip_reputation(self, ip_address: str) -> Tuple[bool, str, int]:
        """
        Check IP address reputation (basic implementation).
        
        Returns:
            Tuple of (is_safe, reason, risk_score)
        """
        risk_score = 0
        reasons = []
        
        try:
            # Check for private/reserved IPs
            ip = ipaddress.ip_address(ip_address)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                reasons.append("Private/Reserved IP address")
                risk_score += 10
            
            # Check for suspicious IP patterns
            # This is a basic implementation - in production, you'd use a proper IP reputation service
            if str(ip).startswith(('192.168.', '10.', '172.16.', '172.31.')):
                reasons.append("Internal network IP")
                risk_score += 5
            
            # Check for known proxy/VPN patterns (basic)
            proxy_patterns = ['proxy', 'vpn', 'tor', 'anonymous']
            ip_str = str(ip)
            for pattern in proxy_patterns:
                if pattern in ip_str.lower():
                    reasons.append(f"Potential proxy/VPN: {pattern}")
                    risk_score += 15
            
        except ValueError:
            reasons.append("Invalid IP address")
            risk_score += 20
        
        is_safe = risk_score < 25
        reason = "; ".join(reasons) if reasons else "IP appears safe"
        
        return is_safe, reason, risk_score
    
    def log_security_event(self, chat_id: int, event_type: str, details: str, 
                           risk_score: int, action_taken: str, ip_address: str = None,
                           user_agent: str = None):
        """Log security event to database."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO security_events 
                (chat_id, event_type, details, risk_score, timestamp, action_taken, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chat_id, event_type, details, risk_score, datetime.now(), 
                action_taken, ip_address, user_agent
            ))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
        finally:
            conn.close()
    
    def update_user_risk_score(self, chat_id: int, risk_score: int, threat_level: str):
        """Update user's risk score in database."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO user_risk_scores 
                (chat_id, risk_score, threat_level, last_updated, warnings_count, blocks_count)
                VALUES (?, ?, ?, ?, 
                    (SELECT warnings_count FROM user_risk_scores WHERE chat_id = ?),
                    (SELECT blocks_count FROM user_risk_scores WHERE chat_id = ?)
                )
            """, (chat_id, risk_score, threat_level, datetime.now(), chat_id, chat_id))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to update user risk score: {e}")
        finally:
            conn.close()
    
    async def handle_security_threat(self, chat_id: int, threat_assessment: Dict[str, Any]) -> str:
        """
        Handle detected security threat based on assessment.
        
        Returns:
            Action taken
        """
        action = threat_assessment['recommended_action']
        risk_score = threat_assessment['risk_score']
        
        if action == 'block':
            # Block the user
            try:
                result = block_user(chat_id=chat_id, reason=f"Security threat: {threat_assessment['threat_level']}")
                if result['success']:
                    self.log_security_event(
                        chat_id, 'user_blocked', 
                        f"Risk score: {risk_score}, threats: {len(threat_assessment['threats_detected'])}",
                        risk_score, 'blocked'
                    )
                    return 'blocked'
            except Exception as e:
                logger.error(f"Failed to block user {chat_id}: {e}")
                return 'block_failed'
        
        elif action == 'warn':
            # Send warning and increase warning count
            self.user_activity[chat_id]['warnings'] += 1
            self.log_security_event(
                chat_id, 'warning_issued',
                f"Risk score: {risk_score}, threats: {len(threat_assessment['threats_detected'])}",
                risk_score, 'warned'
            )
            
            # If user has too many warnings, consider blocking
            if self.user_activity[chat_id]['warnings'] >= self.security_thresholds['max_warnings']:
                return await self.handle_security_threat(chat_id, {
                    'recommended_action': 'block',
                    'risk_score': risk_score + 20,
                    'threats_detected': threat_assessment['threats_detected']
                })
            
            return 'warned'
        
        elif action == 'queue':
            # Queue the download instead of immediate processing
            self.log_security_event(
                chat_id, 'download_queued',
                f"Risk score: {risk_score}, concurrent limit exceeded",
                risk_score, 'queued'
            )
            return 'queued'
        
        else:
            # Allow the action
            self.log_security_event(
                chat_id, 'action_allowed',
                f"Risk score: {risk_score}",
                risk_score, 'allowed'
            )
            return 'allowed'
    
    def get_user_security_status(self, chat_id: int) -> Dict[str, Any]:
        """Get comprehensive security status for a user."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get user risk score
            cur.execute("""
                SELECT risk_score, threat_level, warnings_count, blocks_count, last_updated
                FROM user_risk_scores 
                WHERE chat_id = ?
            """, (chat_id,))
            risk_data = cur.fetchone()
            
            # Get recent security events
            cur.execute("""
                SELECT event_type, details, risk_score, action_taken, timestamp
                FROM security_events 
                WHERE chat_id = ?
                ORDER BY timestamp DESC 
                LIMIT 10
            """, (chat_id,))
            events = [dict(row) for row in cur.fetchall()]
            
            # Get current activity
            user_data = self.user_activity[chat_id]
            current_activity = {
                'recent_downloads': len([
                    t for t in user_data['downloads']
                    if (datetime.now() - t).total_seconds() < 3600
                ]),
                'recent_failures': len([
                    t for t in user_data['failures']
                    if (datetime.now() - t).total_seconds() < 3600
                ]),
                'concurrent_downloads': len(user_data['concurrent']),
                'warnings': user_data['warnings']
            }
            
            return {
                'risk_score': risk_data['risk_score'] if risk_data else 0,
                'threat_level': risk_data['threat_level'] if risk_data else 'low',
                'warnings_count': risk_data['warnings_count'] if risk_data else 0,
                'blocks_count': risk_data['blocks_count'] if risk_data else 0,
                'last_updated': risk_data['last_updated'] if risk_data else None,
                'recent_events': events,
                'current_activity': current_activity
            }
            
        except Exception as e:
            logger.error(f"Error getting user security status: {e}")
            return {'error': str(e)}
        finally:
            conn.close()
    
    def get_security_statistics(self) -> Dict[str, Any]:
        """Get overall security statistics."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get threat distribution
            cur.execute("""
                SELECT threat_level, COUNT(*) as count, AVG(risk_score) as avg_risk
                FROM user_risk_scores 
                GROUP BY threat_level
            """)
            threat_distribution = [dict(row) for row in cur.fetchall()]
            
            # Get recent security events
            cur.execute("""
                SELECT event_type, COUNT(*) as count
                FROM security_events 
                WHERE timestamp >= datetime('now', '-7 days')
                GROUP BY event_type
                ORDER BY count DESC
            """)
            recent_events = [dict(row) for row in cur.fetchall()]
            
            # Get blocked users count
            cur.execute("SELECT COUNT(*) FROM blocked_users")
            blocked_count = cur.fetchone()[0]
            
            return {
                'threat_distribution': threat_distribution,
                'recent_events': recent_events,
                'blocked_users_count': blocked_count,
                'total_users_with_risk': len(threat_distribution)
            }
            
        except Exception as e:
            logger.error(f"Error getting security statistics: {e}")
            return {'error': str(e)}
        finally:
            conn.close()
    
    def cleanup_old_security_data(self, days_to_keep: int = 30):
        """Clean up old security data to maintain performance."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Clean old security events
            cur.execute("""
                DELETE FROM security_events 
                WHERE timestamp < datetime('now', '-{} days')
            """.format(days_to_keep))
            
            # Reset inactive user risk scores
            cur.execute("""
                DELETE FROM user_risk_scores 
                WHERE last_updated < datetime('now', '-{} days')
                AND risk_score < 10
            """.format(days_to_keep))
            
            deleted_events = cur.rowcount
            deleted_risk_scores = cur.rowcount
            
            conn.commit()
            
            logger.info(f"Cleaned up security data: {deleted_events} events, {deleted_risk_scores} risk scores")
            
        except Exception as e:
            logger.error(f"Error cleaning up security data: {e}")
        finally:
            conn.close()


# Global instance for easy access
security_manager = SecurityManager()


async def security_check_before_download(chat_id: int, url: str, **kwargs) -> Tuple[bool, str]:
    """
    Perform comprehensive security check before allowing download.
    
    Returns:
        Tuple of (is_allowed, reason)
    """
    try:
        # URL safety check
        is_url_safe, url_reason, url_risk = security_manager.validate_url_safety(url)
        if not is_url_safe:
            security_manager.log_security_event(
                chat_id, 'malicious_url', url_reason, url_risk, 'blocked'
            )
            return False, f"Unsafe URL: {url_reason}"
        
        # Activity pattern detection
        threat_assessment = security_manager.detect_suspicious_patterns(
            chat_id, 'download', url=url, **kwargs
        )
        
        if threat_assessment['threat_level'] == 'high':
            action = await security_manager.handle_security_threat(chat_id, threat_assessment)
            if action == 'blocked':
                return False, "Access denied due to suspicious activity"
        
        # All checks passed
        return True, "Security check passed"
        
    except Exception as e:
        logger.error(f"Security check error for user {chat_id}: {e}")
        # Default to allowing download if security check fails
        return True, "Security check unavailable"
    

async def record_download_start(chat_id: int, url: str):
    """Record that a download has started for a user."""
    try:
        security_manager.user_activity[chat_id]['concurrent'].add(url)
        
        # Perform activity monitoring
        threat_assessment = security_manager.detect_suspicious_patterns(
            chat_id, 'download', url=url
        )
        
        # Log if there are any concerns
        if threat_assessment['threat_level'] in ['medium', 'high']:
            security_manager.log_security_event(
                chat_id, 'download_start',
                f"URL: {url[:100]}, risk_score: {threat_assessment['risk_score']}",
                threat_assessment['risk_score'],
                'monitored'
            )
            
    except Exception as e:
        logger.error(f"Error recording download start: {e}")


async def record_download_complete(chat_id: int, url: str, success: bool = True):
    """Record that a download has completed."""
    try:
        # Remove from concurrent downloads
        security_manager.user_activity[chat_id]['concurrent'].discard(url)
        
        # Record success/failure
        if not success:
            security_manager.detect_suspicious_patterns(chat_id, 'failure')
            
    except Exception as e:
        logger.error(f"Error recording download completion: {e}")