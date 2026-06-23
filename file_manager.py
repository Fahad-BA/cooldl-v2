"""
Smart File Management System for CoolDL
Provides intelligent file cleanup, storage optimization, and disk space management.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import sqlite3

from config import settings
import db

logger = logging.getLogger(__name__)


class SmartFileCleaner:
    """Intelligent file management with smart cleanup strategies."""
    
    def __init__(self):
        self.download_dir = Path(settings.download.download_dir_path)
        self.db_path = Path(settings.database.absolute_path)
        
        # Cleanup configuration
        self.cleanup_rules = {
            'age_days': settings.rate_limit.file_retention_days,
            'size_mb_threshold': 500,  # Files larger than 500MB get priority cleanup
            'access_threshold_days': 7,  # Files not accessed in 7 days
            'min_free_space_gb': 5,  # Minimum free space to maintain
            'max_cleanup_percent': 20,  # Max 20% of files per cleanup run
        }
        
        # File type priorities (lower = higher priority for keeping)
        self.file_priority = {
            '.mp4': 1,    # Video files - high priority
            '.mp3': 2,    # Audio files - medium priority
            '.webm': 3,
            '.avi': 3,
            '.mkv': 3,
            '.mov': 3,
            '.flv': 4,    # Less common formats
            '.jpg': 5,    # Images - lower priority
            '.png': 5,
            '.jpeg': 5,
        }
        
        self.initialize_file_tracking()
    
    def initialize_file_tracking(self):
        """Initialize file tracking database if not exists."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Create file tracking table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS file_tracking (
                    filename TEXT PRIMARY KEY,
                    filepath TEXT NOT NULL,
                    size_bytes INTEGER,
                    created_at TIMESTAMP,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    downloads INTEGER DEFAULT 0,
                    file_type TEXT,
                    priority INTEGER DEFAULT 10,
                    protected BOOLEAN DEFAULT 0,
                    cleanup_reason TEXT
                )
            """)
            
            # Create indexes for better performance
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_tracking_created_at ON file_tracking(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_tracking_last_accessed ON file_tracking(last_accessed)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_tracking_priority ON file_tracking(priority)")
            
            conn.commit()
            logger.info("File tracking database initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize file tracking: {e}")
        finally:
            conn.close()
    
    def scan_download_directory(self) -> Dict[str, any]:
        """Scan download directory and update file tracking."""
        stats = {
            'total_files': 0,
            'total_size_mb': 0,
            'new_files': 0,
            'removed_files': 0,
            'updated_files': 0
        }
        
        if not self.download_dir.exists():
            logger.warning(f"Download directory does not exist: {self.download_dir}")
            return stats
        
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get all files in download directory
            files_on_disk = set()
            for file_path in self.download_dir.rglob('*'):
                if file_path.is_file():
                    files_on_disk.add(file_path.name)
                    stats['total_files'] += 1
                    stats['total_size_mb'] += file_path.stat().st_size / (1024 * 1024)
            
            # Get all files in database
            cur.execute("SELECT filename FROM file_tracking")
            files_in_db = {row[0] for row in cur.fetchall()}
            
            # Find new files (on disk but not in database)
            new_files = files_on_disk - files_in_db
            for filename in new_files:
                file_path = self.download_dir / filename
                if file_path.exists():
                    file_stat = file_path.stat()
                    file_ext = file_path.suffix.lower()
                    
                    priority = self.file_priority.get(file_ext, 10)
                    
                    cur.execute("""
                        INSERT INTO file_tracking 
                        (filename, filepath, size_bytes, created_at, last_accessed, file_type, priority)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        filename,
                        str(file_path),
                        file_stat.st_size,
                        datetime.fromtimestamp(file_stat.st_ctime),
                        datetime.fromtimestamp(file_stat.st_atime),
                        file_ext,
                        priority
                    ))
                    stats['new_files'] += 1
            
            # Find removed files (in database but not on disk)
            removed_files = files_in_db - files_on_disk
            for filename in removed_files:
                cur.execute("DELETE FROM file_tracking WHERE filename = ?", (filename,))
                stats['removed_files'] += 1
            
            # Update existing files
            for filename in files_on_disk & files_in_db:
                file_path = self.download_dir / filename
                if file_path.exists():
                    file_stat = file_path.stat()
                    cur.execute("""
                        UPDATE file_tracking 
                        SET size_bytes = ?, last_accessed = ?
                        WHERE filename = ?
                    """, (
                        file_stat.st_size,
                        datetime.fromtimestamp(file_stat.st_atime),
                        filename
                    ))
                    stats['updated_files'] += 1
            
            conn.commit()
            logger.info(f"Directory scan completed: {stats}")
            
        except Exception as e:
            logger.error(f"Error scanning download directory: {e}")
        finally:
            conn.close()
        
        return stats
    
    def get_cleanup_candidates(self) -> List[Dict]:
        """Get list of files that are candidates for cleanup."""
        candidates = []
        
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # Get files that match cleanup criteria
            query = """
                SELECT filename, filepath, size_bytes, created_at, last_accessed, 
                       access_count, downloads, file_type, priority
                FROM file_tracking 
                WHERE protected = 0
                ORDER BY priority DESC, last_accessed ASC, created_at ASC
            """
            
            cur.execute(query)
            rows = cur.fetchall()
            
            for row in rows:
                file_data = dict(row)
                
                # Check age-based cleanup
                file_age = datetime.now() - datetime.fromisoformat(file_data['created_at'])
                if file_age.days > self.cleanup_rules['age_days']:
                    file_data['cleanup_reason'] = f'Age: {file_age.days} days'
                    candidates.append(file_data)
                    continue
                
                # Check size-based cleanup for large files
                size_mb = file_data['size_bytes'] / (1024 * 1024)
                if size_mb > self.cleanup_rules['size_mb_threshold']:
                    file_data['cleanup_reason'] = f'Large file: {size_mb:.1f}MB'
                    candidates.append(file_data)
                    continue
                
                # Check access-based cleanup
                last_access = datetime.fromisoformat(file_data['last_accessed'])
                access_age = datetime.now() - last_access
                if access_age.days > self.cleanup_rules['access_threshold_days']:
                    file_data['cleanup_reason'] = f'Not accessed: {access_age.days} days'
                    candidates.append(file_data)
                    continue
            
        except Exception as e:
            logger.error(f"Error getting cleanup candidates: {e}")
        finally:
            conn.close()
        
        return candidates
    
    def get_disk_usage(self) -> Dict[str, any]:
        """Get current disk usage statistics."""
        try:
            disk_usage = os.statvfs(self.download_dir)
            total_space = disk_usage.f_frsize * disk_usage.f_blocks
            free_space = disk_usage.f_frsize * disk_usage.f_bavail
            used_space = total_space - free_space
            
            return {
                'total_gb': total_space / (1024**3),
                'free_gb': free_space / (1024**3),
                'used_gb': used_space / (1024**3),
                'usage_percent': (used_space / total_space) * 100,
                'free_gb_safe': free_space / (1024**3) >= self.cleanup_rules['min_free_space_gb']
            }
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {'error': str(e)}
    
    async def smart_cleanup(self, dry_run: bool = False) -> Dict[str, any]:
        """
        Perform smart file cleanup based on configured rules.
        
        Args:
            dry_run: If True, only show what would be cleaned up
            
        Returns:
            Cleanup statistics
        """
        stats = {
            'total_candidates': 0,
            'cleaned_files': 0,
            'cleaned_size_mb': 0,
            'disk_before': {},
            'disk_after': {},
            'errors': []
        }
        
        # Get disk usage before cleanup
        stats['disk_before'] = self.get_disk_usage()
        
        # Get cleanup candidates
        candidates = self.get_cleanup_candidates()
        stats['total_candidates'] = len(candidates)
        
        if not candidates:
            logger.info("No files need cleanup")
            return stats
        
        # Limit number of files to clean per run
        max_files = max(1, len(candidates) * self.cleanup_rules['max_cleanup_percent'] // 100)
        candidates_to_clean = candidates[:max_files]
        
        logger.info(f"Smart cleanup: {'DRY RUN' if dry_run else 'LIVE'} - {len(candidates_to_clean)} files")
        
        for file_data in candidates_to_clean:
            try:
                filename = file_data['filename']
                file_path = Path(file_data['filepath'])
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would clean: {filename} ({file_data['cleanup_reason']})")
                    stats['cleaned_files'] += 1
                    stats['cleaned_size_mb'] += file_data['size_bytes'] / (1024 * 1024)
                else:
                    # Actually delete the file
                    if file_path.exists():
                        file_size = file_path.stat().st_size
                        
                        # Delete file
                        file_path.unlink()
                        
                        # Remove from database
                        conn = db.get_connection()
                        try:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM file_tracking WHERE filename = ?", (filename,))
                            conn.commit()
                        finally:
                            conn.close()
                        
                        stats['cleaned_files'] += 1
                        stats['cleaned_size_mb'] += file_size / (1024 * 1024)
                        
                        logger.info(f"Cleaned: {filename} ({file_data['cleanup_reason']})")
                    else:
                        logger.warning(f"File not found: {filename}")
                
            except Exception as e:
                error_msg = f"Error cleaning {filename}: {e}"
                stats['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Get disk usage after cleanup
        stats['disk_after'] = self.get_disk_usage()
        
        logger.info(f"Cleanup completed: {stats}")
        return stats
    
    def record_file_access(self, filename: str):
        """Record when a file is accessed (downloaded by user)."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE file_tracking 
                SET last_accessed = ?, access_count = access_count + 1, downloads = downloads + 1
                WHERE filename = ?
            """, (datetime.now(), filename))
            conn.commit()
        except Exception as e:
            logger.error(f"Error recording file access: {e}")
        finally:
            conn.close()
    
    def protect_file(self, filename: str, reason: str = "manual"):
        """Protect a file from being cleaned up."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE file_tracking 
                SET protected = 1, cleanup_reason = ?
                WHERE filename = ?
            """, (f"Protected: {reason}", filename))
            conn.commit()
            logger.info(f"Protected file: {filename} ({reason})")
        except Exception as e:
            logger.error(f"Error protecting file: {e}")
        finally:
            conn.close()
    
    def unprotect_file(self, filename: str):
        """Unprotect a file, making it eligible for cleanup."""
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE file_tracking 
                SET protected = 0, cleanup_reason = NULL
                WHERE filename = ?
            """, (filename,))
            conn.commit()
            logger.info(f"Unprotected file: {filename}")
        except Exception as e:
            logger.error(f"Error unprotecting file: {e}")
        finally:
            conn.close()
    
    def get_file_statistics(self) -> Dict[str, any]:
        """Get comprehensive file statistics."""
        stats = {
            'disk_usage': self.get_disk_usage(),
            'file_counts': {},
            'size_by_type': {},
            'age_distribution': {},
            'cleanup_candidates': len(self.get_cleanup_candidates())
        }
        
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            
            # File count by type
            cur.execute("""
                SELECT file_type, COUNT(*) as count, SUM(size_bytes) as total_size
                FROM file_tracking 
                GROUP BY file_type
                ORDER BY count DESC
            """)
            for row in cur.fetchall():
                stats['file_counts'][row['file_type'] or 'unknown'] = row['count']
                stats['size_by_type'][row['file_type'] or 'unknown'] = row['total_size'] / (1024 * 1024)
            
            # Age distribution
            cur.execute("""
                SELECT 
                    CASE 
                        WHEN julianday('now') - julianday(created_at) <= 7 THEN '0-7 days'
                        WHEN julianday('now') - julianday(created_at) <= 30 THEN '8-30 days'
                        WHEN julianday('now') - julianday(created_at) <= 90 THEN '31-90 days'
                        ELSE '90+ days'
                    END as age_group,
                    COUNT(*) as count,
                    SUM(size_bytes) as total_size
                FROM file_tracking 
                GROUP BY age_group
                ORDER BY age_group
            """)
            for row in cur.fetchall():
                stats['age_distribution'][row['age_group']] = {
                    'count': row['count'],
                    'size_mb': row['total_size'] / (1024 * 1024)
                }
                
        except Exception as e:
            logger.error(f"Error getting file statistics: {e}")
        finally:
            conn.close()
        
        return stats


# Global instance for easy access
file_manager = SmartFileCleaner()


async def run_periodic_cleanup():
    """Run periodic cleanup in the background."""
    logger.info("Starting periodic file cleanup")
    
    try:
        # First scan the directory to update file tracking
        scan_stats = file_manager.scan_download_directory()
        
        # Then run smart cleanup
        cleanup_stats = await file_manager.smart_cleanup(dry_run=False)
        
        # Log results
        if cleanup_stats['cleaned_files'] > 0:
            logger.info(f"Periodic cleanup completed: {cleanup_stats['cleaned_files']} files cleaned, {cleanup_stats['cleaned_size_mb']:.1f}MB freed")
        else:
            logger.info("Periodic cleanup completed: No files needed cleaning")
            
    except Exception as e:
        logger.error(f"Error in periodic cleanup: {e}")


async def start_cleanup_scheduler():
    """Start the cleanup scheduler task."""
    logger.info("Starting cleanup scheduler")
    
    if not settings.cleanup_enabled:
        logger.info("Cleanup is disabled in settings")
        return
    
    while True:
        try:
            # Wait for next cleanup interval
            await asyncio.sleep(settings.cleanup_interval_hours * 3600)
            
            # Run cleanup
            await run_periodic_cleanup()
            
        except asyncio.CancelledError:
            logger.info("Cleanup scheduler cancelled")
            break
        except Exception as e:
            logger.error(f"Error in cleanup scheduler: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying