"""
Intelligent URL Validation & Pre-processing System for CoolDL
Provides smart URL analysis, content type prediction, file size estimation,
platform-specific optimization hints, and early warning system.
"""

import re
import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Predicted content types for URLs."""
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    PLAYLIST = "playlist"
    LIVE_STREAM = "live_stream"
    SHORT_VIDEO = "short_video"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Confidence levels for predictions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class URLAnalysis:
    """Comprehensive URL analysis result."""
    url: str
    normalized_url: str
    platform: str
    content_type: ContentType
    content_type_confidence: ConfidenceLevel
    is_supported: bool
    estimated_size_mb: Optional[float] = None
    size_confidence: ConfidenceLevel = ConfidenceLevel.LOW
    requires_auth: bool = False
    is_live: bool = False
    is_playlist: bool = False
    optimization_hints: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0


class URLValidator:
    """
    Intelligent URL validation and pre-processing system.
    
    Analyzes URLs before downloading to:
    - Predict content type (video, audio, image, playlist)
    - Estimate file size before downloading
    - Provide platform-specific optimization hints
    - Warn about unsupported or problematic content early
    """
    
    # Platform configurations with detailed metadata
    PLATFORM_CONFIGS = {
        'youtube.com': {
            'name': 'YouTube',
            'supported': True,
            'max_video_size_mb': 2048,
            'avg_video_size_mb': 150,
            'supports_audio_extract': True,
            'auth_required': False,
            'rate_limit_sensitive': True,
            'content_hints': {
                '/watch': ContentType.VIDEO,
                '/shorts/': ContentType.SHORT_VIDEO,
                '/live/': ContentType.LIVE_STREAM,
                '/playlist': ContentType.PLAYLIST,
                '/embed/': ContentType.VIDEO,
            }
        },
        'youtu.be': {
            'name': 'YouTube',
            'supported': True,
            'max_video_size_mb': 2048,
            'avg_video_size_mb': 150,
            'supports_audio_extract': True,
            'auth_required': False,
            'rate_limit_sensitive': True,
            'content_hints': {
                '/': ContentType.VIDEO,  # Short links are always videos
            }
        },
        'tiktok.com': {
            'name': 'TikTok',
            'supported': True,
            'max_video_size_mb': 300,
            'avg_video_size_mb': 30,
            'supports_audio_extract': True,
            'auth_required': False,
            'rate_limit_sensitive': True,
            'content_hints': {
                '/@': ContentType.SHORT_VIDEO,
                '/video/': ContentType.SHORT_VIDEO,
                '/t/': ContentType.SHORT_VIDEO,
            }
        },
        'instagram.com': {
            'name': 'Instagram',
            'supported': True,
            'max_video_size_mb': 500,
            'avg_video_size_mb': 80,
            'supports_audio_extract': False,
            'auth_required': True,
            'rate_limit_sensitive': True,
            'content_hints': {
                '/reel/': ContentType.SHORT_VIDEO,
                '/reels/': ContentType.SHORT_VIDEO,
                '/p/': ContentType.VIDEO,
                '/stories/': ContentType.VIDEO,
                '/tv/': ContentType.VIDEO,
            }
        },
        'x.com': {
            'name': 'X (Twitter)',
            'supported': True,
            'max_video_size_mb': 512,
            'avg_video_size_mb': 40,
            'supports_audio_extract': True,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {
                '/status/': ContentType.VIDEO,
            }
        },
        'twitter.com': {
            'name': 'X (Twitter)',
            'supported': True,
            'max_video_size_mb': 512,
            'avg_video_size_mb': 40,
            'supports_audio_extract': True,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {
                '/status/': ContentType.VIDEO,
            }
        },
        'snapchat.com': {
            'name': 'Snapchat',
            'supported': True,
            'max_video_size_mb': 200,
            'avg_video_size_mb': 25,
            'supports_audio_extract': False,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {}
        },
        'tumblr.com': {
            'name': 'Tumblr',
            'supported': True,
            'max_video_size_mb': 100,
            'avg_video_size_mb': 20,
            'supports_audio_extract': False,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {}
        },
        'facebook.com': {
            'name': 'Facebook',
            'supported': False,
            'max_video_size_mb': 0,
            'avg_video_size_mb': 0,
            'supports_audio_extract': False,
            'auth_required': True,
            'rate_limit_sensitive': True,
            'content_hints': {}
        },
        'reddit.com': {
            'name': 'Reddit',
            'supported': False,
            'max_video_size_mb': 0,
            'avg_video_size_mb': 0,
            'supports_audio_extract': False,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {}
        },
        'pinterest.com': {
            'name': 'Pinterest',
            'supported': False,
            'max_video_size_mb': 0,
            'avg_video_size_mb': 0,
            'supports_audio_extract': False,
            'auth_required': False,
            'rate_limit_sensitive': False,
            'content_hints': {}
        },
    }
    
    # Unsupported platform warnings
    UNSUPPORTED_PLATFORM_MSG = {
        'facebook.com': "Facebook requires authentication and is not currently supported.",
        'reddit.com': "Reddit videos are not currently supported. Try YouTube, TikTok, or X.",
        'pinterest.com': "Pinterest is not currently supported. Try Instagram or TikTok.",
        'vimeo.com': "Vimeo is not currently supported.",
        'twitch.tv': "Twitch clips/VODs are not currently supported.",
        'dailymotion.com': "Dailymotion is not currently supported.",
    }
    
    # URL pattern for validation
    URL_PATTERN = re.compile(
        r'^https?://'  # Protocol
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # Domain
        r'localhost|'  # Localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # Port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    # Suspicious URL indicators
    SUSPICIOUS_INDICATORS = [
        r'\.tk/', r'\.ml/', r'\.ga/', r'\.cf/', r'\.gq/',
        r'bit\.ly', r'tinyurl', r'goo\.gl', r't\.co',
        r'redirect', r'forward', r'proxy',
    ]
    
    def __init__(self):
        self._cache: Dict[str, URLAnalysis] = {}
        self._cache_max_size = 500
    
    def _normalize_platform(self, url: str) -> Tuple[str, str]:
        """
        Extract platform name and normalized domain from URL.
        
        Returns:
            Tuple of (platform_key, domain)
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove common prefixes
            for prefix in ['www.', 'm.', 'mobile.', 'web.']:
                if domain.startswith(prefix):
                    domain = domain[len(prefix):]
            
            # Check against known platforms
            for platform_key in self.PLATFORM_CONFIGS:
                if platform_key in domain:
                    return platform_key, domain
            
            return domain, domain
        except Exception:
            return 'unknown', 'unknown'
    
    def _predict_content_type(self, url: str, platform_key: str) -> Tuple[ContentType, ConfidenceLevel]:
        """
        Predict content type based on URL patterns and platform.
        
        Returns:
            Tuple of (content_type, confidence)
        """
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        content_hints = config.get('content_hints', {})
        
        # Check platform-specific path hints
        for path_hint, content_type in content_hints.items():
            if path_hint in url.lower():
                return content_type, ConfidenceLevel.HIGH
        
        # Check query parameters for live streams
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        
        if 'live' in parsed.path.lower() or 'live' in str(query.get('feature', '')).lower():
            return ContentType.LIVE_STREAM, ConfidenceLevel.HIGH
        
        # Check for playlist indicators
        if 'list' in query or 'playlist' in parsed.path.lower():
            return ContentType.PLAYLIST, ConfidenceLevel.MEDIUM
        
        # Platform-based defaults
        platform_name = config.get('name', '')
        if platform_name in ('YouTube', 'TikTok', 'Instagram', 'X (Twitter)'):
            return ContentType.VIDEO, ConfidenceLevel.MEDIUM
        
        return ContentType.UNKNOWN, ConfidenceLevel.LOW
    
    def _estimate_file_size(self, platform_key: str, content_type: ContentType, 
                            url: str) -> Tuple[Optional[float], ConfidenceLevel]:
        """
        Estimate file size based on platform and content type.
        
        Returns:
            Tuple of (estimated_size_mb, confidence)
        """
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        avg_size = config.get('avg_video_size_mb', 0)
        max_size = config.get('max_video_size_mb', 0)
        
        if avg_size == 0:
            return None, ConfidenceLevel.LOW
        
        # Adjust based on content type
        if content_type == ContentType.SHORT_VIDEO:
            # Short videos are typically smaller (TikTok, Reels, Shorts)
            estimated = avg_size * 0.3  # 30% of average full video
            confidence = ConfidenceLevel.MEDIUM
        elif content_type == ContentType.LIVE_STREAM:
            # Live streams can be very large
            estimated = avg_size * 3
            confidence = ConfidenceLevel.LOW
        elif content_type == ContentType.AUDIO:
            # Audio extraction is much smaller
            estimated = avg_size * 0.1
            confidence = ConfidenceLevel.MEDIUM
        elif content_type == ContentType.PLAYLIST:
            # Playlists are unpredictable
            estimated = None
            confidence = ConfidenceLevel.LOW
        else:
            # Standard video
            estimated = avg_size
            confidence = ConfidenceLevel.MEDIUM
        
        # Check if estimated size exceeds max
        if estimated and max_size > 0:
            estimated = min(estimated, max_size)
        
        # Check against bot's max file size
        max_allowed = settings.rate_limit.max_file_size_mb
        if estimated and estimated > max_allowed:
            logger.warning(
                f"Estimated file size {estimated:.1f}MB exceeds max allowed {max_allowed}MB "
                f"for {platform_key}"
            )
        
        return estimated, confidence
    
    def _get_optimization_hints(self, platform_key: str, content_type: ContentType,
                                url: str) -> List[str]:
        """Get platform-specific optimization hints for the download."""
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        hints = []
        
        # Platform-specific hints
        if platform_key in ('youtube.com', 'youtu.be'):
            hints.append("Use fragmented download for better resilience")
            hints.append("Enable concurrent fragment downloads")
            
            if content_type == ContentType.SHORT_VIDEO:
                hints.append("Shorts: prioritize speed over quality")
                hints.append("Use single format (no merge needed)")
            elif content_type == ContentType.LIVE_STREAM:
                hints.append("Live content: use HLS native handler")
                hints.append("Increase timeout for long streams")
        
        elif platform_key == 'tiktok.com':
            hints.append("Use webkit impersonation to bypass restrictions")
            hints.append("Strip tracking parameters")
            hints.append("Direct download - no fragments needed")
        
        elif platform_key == 'instagram.com':
            hints.append("Authentication may be required")
            hints.append("Handle rate limiting carefully")
            if '/reel/' in url or '/reels/' in url:
                hints.append("Reels: optimize for vertical video")
        
        elif platform_key in ('x.com', 'twitter.com'):
            hints.append("Handle variant selection for best quality")
            hints.append("May contain multiple media items")
        
        # Content-type specific hints
        if content_type == ContentType.SHORT_VIDEO:
            hints.append("Skip subtitle extraction")
            hints.append("Minimal post-processing")
        elif content_type == ContentType.LIVE_STREAM:
            hints.append("Stream may end during download")
            hints.append("Consider partial download support")
        elif content_type == ContentType.PLAYLIST:
            hints.append("WARNING: Playlist detected - only first item will download")
        
        # Size-based hints
        estimated_size, _ = self._estimate_file_size(platform_key, content_type, url)
        if estimated_size and estimated_size > 200:
            hints.append(f"Large file (~{estimated_size:.0f}MB) - may take longer")
        
        return hints
    
    def _generate_warnings(self, platform_key: str, content_type: ContentType,
                           url: str, estimated_size: Optional[float]) -> List[str]:
        """Generate warnings for potential issues."""
        warnings = []
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        
        # Unsupported platform warning
        if not config.get('supported', False):
            platform_name = config.get('name', platform_key)
            msg = self.UNSUPPORTED_PLATFORM_MSG.get(
                platform_key, 
                f"{platform_name} is not currently supported."
            )
            warnings.append(msg)
        
        # Authentication warning
        if config.get('auth_required', False):
            warnings.append("This platform may require authentication - download might fail")
        
        # Size warnings
        max_allowed = settings.rate_limit.max_file_size_mb
        if estimated_size:
            if estimated_size > max_allowed:
                warnings.append(
                    f"Estimated size (~{estimated_size:.0f}MB) exceeds maximum allowed ({max_allowed}MB)"
                )
            elif estimated_size > max_allowed * 0.8:
                warnings.append(
                    f"Large file detected (~{estimated_size:.0f}MB) - approaching size limit"
                )
        
        # Live stream warning
        if content_type == ContentType.LIVE_STREAM:
            warnings.append("Live streams may fail if they end during download")
        
        # Playlist warning
        if content_type == ContentType.PLAYLIST:
            warnings.append("Playlist URL detected - only the first video will be downloaded")
        
        # Rate limit sensitive platforms
        if config.get('rate_limit_sensitive', False):
            warnings.append("This platform has strict rate limits - avoid rapid successive downloads")
        
        # Suspicious URL indicators
        url_lower = url.lower()
        for pattern in self.SUSPICIOUS_INDICATORS:
            if re.search(pattern, url_lower):
                warnings.append(f"Suspicious URL pattern detected - proceed with caution")
                break
        
        return warnings
    
    def _validate_url_format(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validate URL format.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not url or not isinstance(url, str):
            return False, "Empty or invalid URL"
        
        url = url.strip()
        
        if len(url) < 10:
            return False, "URL too short"
        
        if len(url) > 2048:
            return False, "URL too long (exceeds 2048 characters)"
        
        if not url.startswith(('http://', 'https://')):
            return False, "URL must start with http:// or https://"
        
        if not self.URL_PATTERN.match(url):
            return False, "Invalid URL format"
        
        return True, None
    
    def _normalize_url(self, url: str) -> str:
        """Basic URL normalization."""
        url = url.strip()
        
        # Ensure https
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        
        # Remove trailing slash unless it's root
        parsed = urlparse(url)
        if parsed.path == '/' and url.endswith('/'):
            url = url[:-1]
        
        return url
    
    async def analyze_url(self, url: str) -> URLAnalysis:
        """
        Perform comprehensive URL analysis.
        
        This is the main entry point for URL validation and pre-processing.
        
        Args:
            url: The URL to analyze
            
        Returns:
            URLAnalysis object with all predictions and warnings
        """
        start_time = datetime.now()
        
        # Check cache first
        if url in self._cache:
            cached = self._cache[url]
            logger.debug(f"URL analysis cache hit: {url}")
            return cached
        
        # Normalize URL
        normalized = self._normalize_url(url)
        
        # Validate format
        is_valid, error_msg = self._validate_url_format(normalized)
        if not is_valid:
            analysis = URLAnalysis(
                url=url,
                normalized_url=normalized,
                platform='unknown',
                content_type=ContentType.UNKNOWN,
                content_type_confidence=ConfidenceLevel.LOW,
                is_supported=False,
                warnings=[f"Invalid URL: {error_msg}"],
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )
            return analysis
        
        # Detect platform
        platform_key, domain = self._normalize_platform(normalized)
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        platform_name = config.get('name', platform_key)
        is_supported = config.get('supported', False)
        
        # Predict content type
        content_type, type_confidence = self._predict_content_type(normalized, platform_key)
        
        # Estimate file size
        estimated_size, size_confidence = self._estimate_file_size(
            platform_key, content_type, normalized
        )
        
        # Generate optimization hints
        optimization_hints = self._get_optimization_hints(
            platform_key, content_type, normalized
        )
        
        # Generate warnings
        warnings = self._generate_warnings(
            platform_key, content_type, normalized, estimated_size
        )
        
        # Build metadata
        metadata = {
            'domain': domain,
            'supports_audio_extract': config.get('supports_audio_extract', False),
            'rate_limit_sensitive': config.get('rate_limit_sensitive', False),
            'platform_max_size_mb': config.get('max_video_size_mb', 0),
            'platform_avg_size_mb': config.get('avg_video_size_mb', 0),
        }
        
        # Detect special properties
        is_live = content_type == ContentType.LIVE_STREAM
        is_playlist = content_type == ContentType.PLAYLIST
        requires_auth = config.get('auth_required', False)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        analysis = URLAnalysis(
            url=url,
            normalized_url=normalized,
            platform=platform_name,
            content_type=content_type,
            content_type_confidence=type_confidence,
            is_supported=is_supported,
            estimated_size_mb=estimated_size,
            size_confidence=size_confidence,
            requires_auth=requires_auth,
            is_live=is_live,
            is_playlist=is_playlist,
            optimization_hints=optimization_hints,
            warnings=warnings,
            metadata=metadata,
            processing_time_ms=processing_time
        )
        
        # Cache the result
        if len(self._cache) >= self._cache_max_size:
            # Simple cache eviction: remove oldest entries
            keys_to_remove = list(self._cache.keys())[:self._cache_max_size // 4]
            for key in keys_to_remove:
                del self._cache[key]
        
        self._cache[url] = analysis
        
        logger.info(
            f"URL analyzed: platform={platform_name}, type={content_type.value}, "
            f"supported={is_supported}, size~{estimated_size}MB, "
            f"time={processing_time:.1f}ms"
        )
        
        return analysis
    
    def get_quick_assessment(self, url: str) -> Dict[str, Any]:
        """
        Synchronous quick assessment for immediate feedback.
        
        Returns a simplified dict for fast checks.
        """
        platform_key, _ = self._normalize_platform(url)
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        
        return {
            'platform': config.get('name', 'Unknown'),
            'supported': config.get('supported', False),
            'avg_size_mb': config.get('avg_video_size_mb', 0),
            'auth_required': config.get('auth_required', False),
        }
    
    def is_likely_supported(self, url: str) -> bool:
        """Quick check if URL is from a supported platform."""
        platform_key, _ = self._normalize_platform(url)
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        return config.get('supported', False)
    
    def get_platform_info(self, url: str) -> Dict[str, Any]:
        """Get detailed platform information for a URL."""
        platform_key, domain = self._normalize_platform(url)
        config = self.PLATFORM_CONFIGS.get(platform_key, {})
        
        return {
            'platform_key': platform_key,
            'platform_name': config.get('name', 'Unknown'),
            'domain': domain,
            'supported': config.get('supported', False),
            'max_video_size_mb': config.get('max_video_size_mb', 0),
            'avg_video_size_mb': config.get('avg_video_size_mb', 0),
            'supports_audio_extract': config.get('supports_audio_extract', False),
            'auth_required': config.get('auth_required', False),
            'rate_limit_sensitive': config.get('rate_limit_sensitive', False),
        }
    
    def format_analysis_for_user(self, analysis: URLAnalysis) -> str:
        """
        Format analysis results as user-friendly message.
        """
        lines = []
        
        # Platform and support status
        status_emoji = "✅" if analysis.is_supported else "❌"
        lines.append(f"{status_emoji} **{analysis.platform}**")
        
        # Content type
        type_emoji = {
            ContentType.VIDEO: "🎥",
            ContentType.SHORT_VIDEO: "📱",
            ContentType.AUDIO: "🎵",
            ContentType.LIVE_STREAM: "🔴",
            ContentType.PLAYLIST: "📋",
            ContentType.IMAGE: "🖼️",
            ContentType.UNKNOWN: "❓",
        }.get(analysis.content_type, "📦")
        
        lines.append(f"{type_emoji} Type: {analysis.content_type.value.replace('_', ' ').title()}")
        
        # Size estimate
        if analysis.estimated_size_mb:
            size_str = f"~{analysis.estimated_size_mb:.0f}MB"
            if analysis.size_confidence == ConfidenceLevel.LOW:
                size_str += " (rough estimate)"
            lines.append(f"📏 Size: {size_str}")
        
        # Warnings
        if analysis.warnings:
            lines.append("")
            for warning in analysis.warnings:
                lines.append(f"⚠️ {warning}")
        
        return "\n".join(lines)


# Global instance for easy access
url_validator = URLValidator()


async def validate_and_analyze(url: str) -> URLAnalysis:
    """
    Convenience function to validate and analyze a URL.
    
    Args:
        url: URL to analyze
        
    Returns:
        URLAnalysis object with complete analysis
    """
    return await url_validator.analyze_url(url)


async def pre_download_check(url: str) -> Tuple[bool, str, Optional[URLAnalysis]]:
    """
    Quick pre-download validation check.
    
    Returns:
        Tuple of (should_proceed, reason, analysis)
        - should_proceed: True if download should continue
        - reason: Explanation of decision
        - analysis: Full URL analysis if performed
    """
    try:
        analysis = await url_validator.analyze_url(url)
        
        if not analysis.is_supported:
            return False, f"Platform not supported: {analysis.platform}", analysis
        
        if analysis.estimated_size_mb and analysis.estimated_size_mb > settings.rate_limit.max_file_size_mb:
            return False, (
                f"File too large (~{analysis.estimated_size_mb:.0f}MB). "
                f"Maximum is {settings.rate_limit.max_file_size_mb}MB."
            ), analysis
        
        return True, "URL validated successfully", analysis
        
    except Exception as e:
        logger.error(f"Pre-download check error: {e}")
        return True, "Validation skipped (error)", None
