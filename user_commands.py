"""
Enhanced User Commands for CoolDL Phase 2
Provides new bot commands for statistics, health monitoring, queue status,
manual cleanup, security status, and enhanced help with interactive examples.
"""

import logging
import os
import psutil
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import settings
import db
from file_manager import file_manager
from security_manager import security_manager
from error_recovery import error_recovery

logger = logging.getLogger(__name__)

# Admin chat IDs - these users have access to admin commands
# Uses the same blocking system's admin concept
ADMIN_IDS = set()

# Try to load admin IDs from environment
admin_env = os.getenv('ADMIN_IDS', '')
if admin_env:
    try:
        ADMIN_IDS = set(int(x.strip()) for x in admin_env.split(',') if x.strip())
    except ValueError:
        logger.warning("Invalid ADMIN_IDS format in environment")

# Fallback: treat the bot owner as admin (can be configured)
OWNER_ID = os.getenv('OWNER_CHAT_ID', '')
if OWNER_ID:
    try:
        ADMIN_IDS.add(int(OWNER_ID))
    except ValueError:
        pass


def is_admin(chat_id: int) -> bool:
    """Check if user is an admin."""
    return chat_id in ADMIN_IDS


# ==================== /stats COMMAND ====================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show user's personal download statistics.
    
    Displays:
    - Total downloads
    - Downloads by platform
    - Recent activity
    - Account age
    - Success rate
    """
    try:
        chat_id = update.effective_chat.id
        conn = db.get_connection()
        cur = conn.cursor()
        
        # Get user info
        cur.execute("SELECT name, username, created_at FROM users WHERE chat_id = ?", (chat_id,))
        user_info = cur.fetchone()
        
        if not user_info:
            await update.message.reply_text(
                "📊 You don't have any download history yet.\n"
                "Send a video link to get started!"
            )
            conn.close()
            return
        
        name = user_info['name'] or 'User'
        username = user_info['username'] or 'N/A'
        created_at = user_info['created_at'] or 'Unknown'
        
        # Get total downloads
        cur.execute("SELECT COUNT(*) as count FROM downloads WHERE chat_id = ?", (chat_id,))
        total_downloads = cur.fetchone()['count']
        
        # Get downloads by platform
        cur.execute("""
            SELECT source, COUNT(*) as count, SUM(file_size) as total_size
            FROM downloads 
            WHERE chat_id = ?
            GROUP BY source 
            ORDER BY count DESC
        """, (chat_id,))
        platform_stats = [dict(row) for row in cur.fetchall()]
        
        # Get recent downloads (last 5)
        cur.execute("""
            SELECT source, filename, timestamp, file_size
            FROM downloads 
            WHERE chat_id = ?
            ORDER BY rowid DESC 
            LIMIT 5
        """, (chat_id,))
        recent_downloads = [dict(row) for row in cur.fetchall()]
        
        # Get error count
        cur.execute("SELECT COUNT(*) as count FROM errors WHERE chat_id = ?", (chat_id,))
        error_count = cur.fetchone()['count']
        
        # Calculate success rate
        total_attempts = total_downloads + error_count
        success_rate = (total_downloads / total_attempts * 100) if total_attempts > 0 else 0
        
        # Get downloads in last 24h
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        cur.execute("""
            SELECT COUNT(*) as count FROM downloads 
            WHERE chat_id = ? AND timestamp >= ?
        """, (chat_id, yesterday))
        recent_24h = cur.fetchone()['count']
        
        # Get downloads in last 7 days
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT COUNT(*) as count FROM downloads 
            WHERE chat_id = ? AND timestamp >= ?
        """, (chat_id, week_ago))
        recent_7d = cur.fetchone()['count']
        
        conn.close()
        
        # Build message
        lines = [
            f"📊 **Your Download Statistics**\n",
            f"👤 **Name:** {name}",
            f"📱 **Username:** @{username}" if username != 'N/A' else "",
            f"📅 **Member since:** {created_at[:10] if created_at else 'Unknown'}\n",
            f"━━━━━━━━━━━━━━━━━━\n",
            f"📥 **Total Downloads:** {total_downloads}",
            f"⏱️ **Last 24h:** {recent_24h}",
            f"📅 **Last 7 days:** {recent_7d}",
            f"❌ **Failed attempts:** {error_count}",
            f"✅ **Success rate:** {success_rate:.1f}%\n",
        ]
        
        # Platform breakdown
        if platform_stats:
            lines.append("━━━━━━━━━━━━━━━━━━")
            lines.append("📱 **By Platform:**")
            for stat in platform_stats:
                source = stat['source'] or 'Unknown'
                count = stat['count']
                size_mb = (stat['total_size'] or 0) / (1024 * 1024)
                size_str = f" ({size_mb:.1f}MB)" if size_mb > 0 else ""
                lines.append(f"  • {source}: {count} downloads{size_str}")
        
        # Recent activity
        if recent_downloads:
            lines.append("\n━━━━━━━━━━━━━━━━━━")
            lines.append("🕐 **Recent Downloads:**")
            for dl in recent_downloads:
                source = dl['source'] or '?'
                ts = dl['timestamp'] or ''
                ts_short = ts[:10] if ts else 'N/A'
                size = dl['file_size'] or 0
                size_str = f" ({size / (1024*1024):.1f}MB)" if size > 0 else ""
                lines.append(f"  • [{ts_short}] {source}{size_str}")
        
        # Remaining quota
        remaining = settings.rate_limit.max_downloads_per_hour  # Simplified
        lines.append(f"\n━━━━━━━━━━━━━━━━━━")
        lines.append(f"⚡ **Hourly limit:** {settings.rate_limit.max_downloads_per_hour}/hour")
        
        # Filter empty lines
        message = "\n".join(line for line in lines if line is not None)
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ Failed to retrieve statistics. Please try again later.")


# ==================== /health COMMAND ====================

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show system health status.
    
    Displays:
    - Bot uptime
    - CPU/Memory usage
    - Disk space
    - Database status
    - Active downloads
    - System warnings
    """
    try:
        chat_id = update.effective_chat.id
        lines = ["🏥 **System Health Status**\n"]
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = "🟢" if cpu_percent < 70 else "🟡" if cpu_percent < 90 else "🔴"
        lines.append(f"{cpu_status} **CPU:** {cpu_percent:.1f}%")
        
        # Memory usage
        mem = psutil.virtual_memory()
        mem_status = "🟢" if mem.percent < 70 else "🟡" if mem.percent < 90 else "🔴"
        mem_gb = mem.used / (1024**3)
        mem_total_gb = mem.total / (1024**3)
        lines.append(f"{mem_status} **Memory:** {mem.percent:.1f}% ({mem_gb:.1f}/{mem_total_gb:.1f}GB)")
        
        # Disk space
        disk_info = file_manager.get_disk_usage()
        if 'error' not in disk_info:
            free_gb = disk_info.get('free_gb', 0)
            used_gb = disk_info.get('used_gb', 0)
            total_gb = disk_info.get('total_gb', 0)
            usage_pct = disk_info.get('usage_percent', 0)
            disk_status = "🟢" if usage_pct < 80 else "🟡" if usage_pct < 95 else "🔴"
            lines.append(f"{disk_status} **Disk:** {usage_pct:.1f}% ({free_gb:.1f}GB free / {total_gb:.1f}GB)")
        else:
            lines.append("🔴 **Disk:** Unable to read")
        
        # Database status
        try:
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM downloads")
            total_dl = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]
            conn.close()
            lines.append(f"🟢 **Database:** Online ({total_dl} downloads, {total_users} users)")
        except Exception:
            lines.append("🔴 **Database:** Connection error")
        
        # File tracking stats
        try:
            file_stats = file_manager.get_file_statistics()
            cleanup_candidates = file_stats.get('cleanup_candidates', 0)
            lines.append(f"📁 **Files tracked:** {cleanup_candidates} cleanup candidates")
        except Exception:
            pass
        
        # Security status
        try:
            sec_stats = security_manager.get_security_statistics()
            blocked_count = sec_stats.get('blocked_users_count', 0)
            lines.append(f"🔒 **Security:** {blocked_count} blocked users")
        except Exception:
            pass
        
        # Bot configuration
        lines.append(f"\n━━━━━━━━━━━━━━━━━━")
        lines.append(f"⚙️ **Configuration:**")
        lines.append(f"  • Max concurrent: {settings.rate_limit.max_concurrent}")
        lines.append(f"  • Max file size: {settings.rate_limit.max_file_size_mb}MB")
        lines.append(f"  • Hourly limit: {settings.rate_limit.max_downloads_per_hour}")
        lines.append(f"  • Timeout: {settings.download.timeout_seconds}s")
        
        # Overall status
        lines.append(f"\n━━━━━━━━━━━━━━━━━━")
        issues = 0
        if cpu_percent > 80:
            issues += 1
        if mem.percent > 85:
            issues += 1
        if 'error' not in disk_info and disk_info.get('usage_percent', 0) > 90:
            issues += 1
        
        if issues == 0:
            lines.append("✅ **All systems operational**")
        elif issues <= 1:
            lines.append("🟡 **Minor issues detected**")
        else:
            lines.append("🔴 **Multiple issues - attention required**")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in health command: {e}")
        await update.message.reply_text("❌ Failed to get health status.")


# ==================== /queue COMMAND ====================

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show current download queue status.
    
    Displays:
    - Active downloads
    - Queue position (if queued)
    - Estimated wait time
    - Concurrent download slots
    """
    try:
        from async_downloader import download_semaphore
        
        chat_id = update.effective_chat.id
        
        # Get semaphore info (how many slots are in use)
        # asyncio.Semaphore doesn't expose internal count directly,
        # but we can track active downloads through security manager
        max_concurrent = settings.rate_limit.max_concurrent
        
        # Get active downloads from security manager
        active_downloads = 0
        user_active = 0
        
        try:
            for uid, activity in security_manager.user_activity.items():
                active = len(activity.get('concurrent', set()))
                active_downloads += active
                if uid == chat_id:
                    user_active = active
        except Exception:
            pass
        
        available_slots = max(0, max_concurrent - active_downloads)
        
        lines = ["📋 **Download Queue Status**\n"]
        
        # Overall queue status
        lines.append(f"🔄 **Active downloads:** {active_downloads}/{max_concurrent}")
        lines.append(f"✅ **Available slots:** {available_slots}")
        
        # User's downloads
        if user_active > 0:
            lines.append(f"\n👤 **Your active downloads:** {user_active}")
            lines.append("Your download is being processed...")
        else:
            lines.append(f"\n👤 **Your active downloads:** 0")
            if available_slots > 0:
                lines.append("✅ Slots available - send a URL to download!")
            else:
                lines.append("⏳ Queue is full - please wait for a slot")
        
        # Rate limit info
        lines.append(f"\n━━━━━━━━━━━━━━━━━━")
        lines.append(f"⚡ **Rate Limits:**")
        lines.append(f"  • Max concurrent: {max_concurrent}")
        lines.append(f"  • Hourly limit: {settings.rate_limit.max_downloads_per_hour}/hour")
        
        # Estimated wait time if queue is full
        if available_slots == 0:
            avg_download_time = settings.download.timeout_seconds // 2  # Rough estimate
            estimated_wait = avg_download_time
            lines.append(f"\n⏱️ **Estimated wait:** ~{estimated_wait}s")
            lines.append("You'll be notified when your download starts.")
        
        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in queue command: {e}")
        await update.message.reply_text("❌ Failed to get queue status.")


# ==================== /cleanup COMMAND (ADMIN) ====================

async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual file cleanup command (admin only).
    
    Usage:
        /cleanup - Dry run (see what would be cleaned)
        /cleanup run - Execute cleanup
        /cleanup scan - Scan and update file tracking
        /cleanup stats - Show file statistics
    """
    try:
        chat_id = update.effective_chat.id
        
        if not is_admin(chat_id):
            await update.message.reply_text("⛔ Admin access required for this command.")
            return
        
        args = context.args if context.args else []
        action = args[0].lower() if args else 'dry'
        
        if action == 'scan':
            # Scan download directory
            await update.message.reply_text("🔍 Scanning download directory...")
            stats = file_manager.scan_download_directory()
            
            message = (
                "📂 **Scan Complete**\n\n"
                f"📁 Total files: {stats['total_files']}\n"
                f"💾 Total size: {stats['total_size_mb']:.1f}MB\n"
                f"🆕 New files: {stats['new_files']}\n"
                f"🗑️ Removed files: {stats['removed_files']}\n"
                f"🔄 Updated files: {stats['updated_files']}"
            )
            await update.message.reply_text(message, parse_mode='Markdown')
            
        elif action == 'run':
            # Execute actual cleanup
            await update.message.reply_text("🧹 Running cleanup...")
            
            # First scan to update tracking
            file_manager.scan_download_directory()
            
            # Run cleanup
            stats = await file_manager.smart_cleanup(dry_run=False)
            
            freed_mb = stats['cleaned_size_mb']
            cleaned = stats['cleaned_files']
            errors = len(stats.get('errors', []))
            
            message = (
                "✅ **Cleanup Complete**\n\n"
                f"🗑️ Files cleaned: {cleaned}\n"
                f"💾 Space freed: {freed_mb:.1f}MB\n"
            )
            
            if errors > 0:
                message += f"⚠️ Errors: {errors}\n"
                for err in stats['errors'][:3]:
                    message += f"  • {err}\n"
            
            if stats.get('disk_before') and stats.get('disk_after'):
                before_free = stats['disk_before'].get('free_gb', 0)
                after_free = stats['disk_after'].get('free_gb', 0)
                diff = after_free - before_free
                message += f"\n💾 Disk: {before_free:.1f}GB → {after_free:.1f}GB (+{diff:.1f}GB)"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        elif action == 'stats':
            # Show file statistics
            stats = file_manager.get_file_statistics()
            
            message = "📊 **File Statistics**\n\n"
            
            # Disk usage
            disk = stats.get('disk_usage', {})
            if 'error' not in disk:
                message += f"💾 **Disk:** {disk.get('usage_percent', 0):.1f}% used ({disk.get('free_gb', 0):.1f}GB free)\n"
            
            # File types
            message += "\n📁 **By Type:**\n"
            for ftype, count in stats.get('file_counts', {}).items():
                size_mb = stats.get('size_by_type', {}).get(ftype, 0)
                message += f"  • {ftype}: {count} files ({size_mb:.1f}MB)\n"
            
            # Age distribution
            message += "\n📅 **By Age:**\n"
            for age_group, data in stats.get('age_distribution', {}).items():
                message += f"  • {age_group}: {data['count']} files ({data['size_mb']:.1f}MB)\n"
            
            # Cleanup candidates
            message += f"\n🗑️ **Cleanup candidates:** {stats.get('cleanup_candidates', 0)}"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        else:
            # Dry run (default)
            await update.message.reply_text("🔍 Running dry-run cleanup analysis...")
            
            # First scan to update tracking
            file_manager.scan_download_directory()
            
            # Dry run cleanup
            stats = await file_manager.smart_cleanup(dry_run=True)
            
            message = (
                "🔍 **Dry Run Results** (no files deleted)\n\n"
                f"🗑️ Would clean: {stats['cleaned_files']} files\n"
                f"💾 Would free: {stats['cleaned_size_mb']:.1f}MB\n"
                f"📊 Total candidates: {stats['total_candidates']}\n\n"
                f"Use `/cleanup run` to execute."
            )
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in cleanup command: {e}")
        await update.message.reply_text("❌ Cleanup operation failed.")


# ==================== /security COMMAND (ADMIN) ====================

async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Security status command (admin only).
    
    Usage:
        /security - Overview of security status
        /security user <chat_id> - Check specific user
        /security events - Recent security events
        /security cleanup - Clean old security data
    """
    try:
        chat_id = update.effective_chat.id
        
        if not is_admin(chat_id):
            await update.message.reply_text("⛔ Admin access required for this command.")
            return
        
        args = context.args if context.args else []
        action = args[0].lower() if args else 'overview'
        
        if action == 'user' and len(args) > 1:
            # Check specific user
            try:
                target_chat_id = int(args[1])
            except ValueError:
                await update.message.reply_text("❌ Invalid chat_id. Use: /security user <chat_id>")
                return
            
            user_status = security_manager.get_user_security_status(target_chat_id)
            
            if 'error' in user_status:
                await update.message.reply_text(f"❌ Error: {user_status['error']}")
                return
            
            message = (
                f"🔒 **Security Status for {target_chat_id}**\n\n"
                f"⚠️ **Risk Score:** {user_status.get('risk_score', 0)}\n"
                f"🎯 **Threat Level:** {user_status.get('threat_level', 'unknown')}\n"
                f"📝 **Warnings:** {user_status.get('warnings_count', 0)}\n"
                f"🚫 **Blocks:** {user_status.get('blocks_count', 0)}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Current Activity:**\n"
                f"  • Recent downloads (1h): {user_status.get('current_activity', {}).get('recent_downloads', 0)}\n"
                f"  • Recent failures (1h): {user_status.get('current_activity', {}).get('recent_failures', 0)}\n"
                f"  • Concurrent: {user_status.get('current_activity', {}).get('concurrent_downloads', 0)}\n"
            )
            
            # Recent events
            events = user_status.get('recent_events', [])
            if events:
                message += f"\n━━━━━━━━━━━━━━━━━━\n"
                message += f"🕐 **Recent Events:**\n"
                for evt in events[:5]:
                    message += (
                        f"  • [{evt.get('action_taken', '?')}] "
                        f"{evt.get('event_type', '?')} "
                        f"(risk: {evt.get('risk_score', 0)})\n"
                    )
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        elif action == 'events':
            # Recent security events
            stats = security_manager.get_security_statistics()
            
            message = "🔒 **Security Events (Last 7 Days)**\n\n"
            
            events = stats.get('recent_events', [])
            if events:
                for evt in events:
                    message += f"  • {evt.get('event_type', '?')}: {evt.get('count', 0)} times\n"
            else:
                message += "No security events recorded.\n"
            
            # Threat distribution
            message += f"\n━━━━━━━━━━━━━━━━━━\n"
            message += f"📊 **Threat Distribution:**\n"
            for threat in stats.get('threat_distribution', []):
                message += (
                    f"  • {threat.get('threat_level', '?')}: "
                    f"{threat.get('count', 0)} users "
                    f"(avg risk: {threat.get('avg_risk', 0):.0f})\n"
                )
            
            message += f"\n🚫 **Total blocked users:** {stats.get('blocked_users_count', 0)}"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        elif action == 'cleanup':
            # Clean old security data
            security_manager.cleanup_old_security_data(days_to_keep=30)
            await update.message.reply_text("✅ Security data cleanup complete (30+ day old records removed).")
            
        else:
            # Overview (default)
            stats = security_manager.get_security_statistics()
            
            message = (
                "🔒 **Security Overview**\n\n"
                f"🚫 **Blocked users:** {stats.get('blocked_users_count', 0)}\n"
                f"👥 **Users with risk scores:** {stats.get('total_users_with_risk', 0)}\n"
            )
            
            # Threat distribution
            threats = stats.get('threat_distribution', [])
            if threats:
                message += f"\n📊 **Threat Levels:**\n"
                for threat in threats:
                    level = threat.get('threat_level', 'unknown')
                    count = threat.get('count', 0)
                    emoji = {'low': '🟢', 'medium': '🟡', 'high': '🔴'}.get(level, '⚪')
                    message += f"  {emoji} {level}: {count} users\n"
            
            # Recent events summary
            events = stats.get('recent_events', [])
            if events:
                message += f"\n🕐 **Recent Events (7d):**\n"
                total_events = sum(e.get('count', 0) for e in events)
                message += f"  Total: {total_events} events\n"
                for evt in events[:5]:
                    message += f"  • {evt.get('event_type', '?')}: {evt.get('count', 0)}\n"
            
            message += f"\n━━━━━━━━━━━━━━━━━━\n"
            message += f"💡 **Commands:**\n"
            message += f"  • /security user <chat_id>\n"
            message += f"  • /security events\n"
            message += f"  • /security cleanup\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in security command: {e}")
        await update.message.reply_text("❌ Failed to get security status.")


# ==================== ENHANCED /help COMMAND ====================

async def enhanced_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Enhanced help command with interactive examples and detailed guides.
    
    Shows platform-specific help, examples, and tips.
    """
    args = context.args if context.args else []
    
    if not args:
        # Main help menu
        keyboard = [
            [
                InlineKeyboardButton("🎥 Platforms", callback_data="help_platforms"),
                InlineKeyboardButton("📋 Commands", callback_data="help_commands"),
            ],
            [
                InlineKeyboardButton("💡 Examples", callback_data="help_examples"),
                InlineKeyboardButton("⚙️ Limits", callback_data="help_limits"),
            ],
            [
                InlineKeyboardButton("❓ FAQ", callback_data="help_faq"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            "📥 **CoolDL Bot Help**\n\n"
            "I can download videos from various platforms for you!\n\n"
            "**Quick Start:** Just send me a video link 🔗\n\n"
            "Select a topic below to learn more:"
        )
        
        await update.message.reply_text(
            message, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    topic = args[0].lower()
    message = _get_help_topic(topic)
    await update.message.reply_text(message, parse_mode='Markdown')


async def help_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks for help menu."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    message = _get_help_topic(data.replace('help_', ''))
    
    await query.edit_message_text(message, parse_mode='Markdown')


def _get_help_topic(topic: str) -> str:
    """Get help text for a specific topic."""
    
    if topic == 'platforms':
        return (
            "🎥 **Supported Platforms**\n\n"
            "✅ **YouTube** - Videos, Shorts, Live\n"
            "   Send any YouTube link\n\n"
            "✅ **TikTok** - Videos\n"
            "   Send TikTok video links\n\n"
            "✅ **Instagram** - Reels, Posts, Stories\n"
            "   Send Instagram links (may need cookies)\n\n"
            "✅ **X (Twitter)** - Videos\n"
            "   Send tweet links with videos\n\n"
            "✅ **Snapchat** - Spotlight videos\n"
            "   Send Snapchat links\n\n"
            "✅ **Tumblr** - Video posts\n"
            "   Send Tumblr video links\n\n"
            "❌ **Not supported:** Facebook, Reddit, Pinterest\n"
            "   (Coming in future updates)"
        )
    
    elif topic == 'commands':
        return (
            "📋 **Available Commands**\n\n"
            "**User Commands:**\n"
            "• `/start` - Start using the bot\n"
            "• `/help` - Show this help menu\n"
            "• `/stats` - Your download statistics\n"
            "• `/health` - System health status\n"
            "• `/queue` - Download queue status\n"
            "• `/status` - Quick bot status\n\n"
            "**Admin Commands:**\n"
            "• `/cleanup [run|scan|stats]` - File management\n"
            "• `/security [user|events|cleanup]` - Security status\n"
            "• `/block <id>` - Block a user\n"
            "• `/unblock <id>` - Unblock a user\n"
            "• `/blocked` - List blocked users\n"
            "• `/check <chat_id>` - Check block status\n\n"
            "💡 **Pro tip:** Just send a URL to download!"
        )
    
    elif topic == 'examples':
        return (
            "💡 **Usage Examples**\n\n"
            "**YouTube:**\n"
            "```\nhttps://youtube.com/watch?v=dQw4w9WgXcQ\n```\n\n"
            "**YouTube Shorts:**\n"
            "```\nhttps://youtube.com/shorts/abc123\n```\n\n"
            "**TikTok:**\n"
            "```\nhttps://tiktok.com/@user/video/123456\n```\n\n"
            "**Instagram Reel:**\n"
            "```\nhttps://instagram.com/reel/abc123/\n```\n\n"
            "**X (Twitter):**\n"
            "```\nhttps://x.com/user/status/123456\n```\n\n"
            "📌 Just paste the link and send - I'll handle the rest!"
        )
    
    elif topic == 'limits':
        max_size = settings.rate_limit.max_file_size_mb
        max_hourly = settings.rate_limit.max_downloads_per_hour
        max_concurrent = settings.rate_limit.max_concurrent
        timeout = settings.download.timeout_seconds
        
        return (
            "⚙️ **Bot Limits & Configuration**\n\n"
            f"📊 **Max file size:** {max_size}MB\n"
            f"⚡ **Max downloads/hour:** {max_hourly}\n"
            f"🔄 **Concurrent downloads:** {max_concurrent}\n"
            f"⏱️ **Download timeout:** {timeout}s\n"
            f"📁 **File retention:** {settings.rate_limit.file_retention_days} days\n\n"
            "**Tips:**\n"
            "• Large files take longer to process\n"
            "• Rate limits reset every hour\n"
            "• Cached downloads are instant!\n"
            "• Files are auto-cleaned after retention period"
        )
    
    elif topic == 'faq':
        return (
            "❓ **Frequently Asked Questions**\n\n"
            "**Q: Why did my download fail?**\n"
            "A: Common reasons: server timeout, rate limiting, or the video was removed. Try again in a few minutes.\n\n"
            "**Q: Can I download playlists?**\n"
            "A: Only the first video from a playlist will be downloaded.\n\n"
            "**Q: Why is my download slow?**\n"
            "A: Large files, server load, or network conditions affect speed. Live streams may take longer.\n\n"
            "**Q: How long are files kept?**\n"
            f"A: Files are retained for {settings.rate_limit.file_retention_days} days, then automatically cleaned.\n\n"
            "**Q: Is there a file size limit?**\n"
            f"A: Yes, maximum file size is {settings.rate_limit.max_file_size_mb}MB.\n\n"
            "**Q: Why can't I download from Facebook/Reddit?**\n"
            "A: These platforms aren't currently supported. Supported: YouTube, TikTok, Instagram, X, Snapchat, Tumblr."
        )
    
    return "Topic not found. Use /help to see available topics."


# ==================== HANDLER REGISTRATION ====================

def get_user_command_handlers():
    """
    Return list of user command handlers for Phase 2.
    
    Returns:
        List of (command_name, handler_function) tuples
    """
    return [
        ('stats', stats_command),
        ('health', health_command),
        ('queue', queue_command),
        ('cleanup', cleanup_command),
        ('security', security_command),
        ('help', enhanced_help_command),  # Override existing help
    ]


def get_callback_handlers():
    """
    Return list of callback query handlers for inline keyboards.
    
    Returns:
        List of (pattern, handler_function) tuples
    """
    return [
        (r'^help_', help_callback_handler),
    ]
