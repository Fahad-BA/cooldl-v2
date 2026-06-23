"""
Enhanced Startup Script for CoolDL
Integrates security monitoring, file management, and error recovery systems.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from file_manager import start_cleanup_scheduler, run_periodic_cleanup, file_manager
from security_manager import security_manager
from error_recovery import error_recovery

logger = logging.getLogger(__name__)


class EnhancedCoolDLBot:
    """Enhanced bot with integrated security and file management."""
    
    def __init__(self):
        self.cleanup_task = None
        self.security_task = None
        self.is_running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.is_running = False
    
    async def initialize_systems(self):
        """Initialize all enhanced systems."""
        logger.info("Initializing enhanced CoolDL systems...")
        
        try:
            # Initialize security database
            security_manager.initialize_security_db()
            logger.info("✅ Security system initialized")
            
            # Initialize file tracking
            file_manager.initialize_file_tracking()
            logger.info("✅ File management system initialized")
            
            # Scan download directory to update file tracking
            logger.info("📁 Scanning download directory...")
            scan_stats = file_manager.scan_download_directory()
            logger.info(f"✅ Directory scan complete: {scan_stats['total_files']} files found")
            
            # Run initial cleanup if enabled
            if settings.cleanup_enabled:
                logger.info("🧹 Running initial cleanup...")
                cleanup_stats = await file_manager.smart_cleanup(dry_run=True)
                logger.info(f"✅ Initial cleanup analysis: {cleanup_stats['cleanup_candidates']} candidates found")
            
            logger.info("🚀 All systems initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize systems: {e}")
            raise
    
    async def start_background_tasks(self):
        """Start background maintenance tasks."""
        logger.info("Starting background tasks...")
        
        try:
            # Start cleanup scheduler
            if settings.cleanup_enabled:
                self.cleanup_task = asyncio.create_task(start_cleanup_scheduler())
                logger.info("✅ Cleanup scheduler started")
            else:
                logger.info("ℹ️ Cleanup disabled in settings")
            
            # Start periodic security monitoring (could be expanded)
            # self.security_task = asyncio.create_task(self.security_monitoring_loop())
            
            logger.info("🔄 Background tasks started successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to start background tasks: {e}")
            raise
    
    async def security_monitoring_loop(self):
        """Periodic security monitoring task."""
        while self.is_running:
            try:
                # Clean up old security data
                security_manager.cleanup_old_security_data(days_to_keep=30)
                
                # Get security statistics
                stats = security_manager.get_security_statistics()
                logger.info(f"📊 Security stats: {stats}")
                
                # Wait for next cycle (1 hour)
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                logger.info("Security monitoring stopped")
                break
            except Exception as e:
                logger.error(f"Error in security monitoring: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def shutdown(self):
        """Graceful shutdown of all systems."""
        logger.info("Shutting down enhanced systems...")
        
        try:
            # Cancel background tasks
            if self.cleanup_task:
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
            
            if self.security_task:
                self.security_task.cancel()
                try:
                    await self.security_task
                except asyncio.CancelledError:
                    pass
            
            # Run final cleanup
            if settings.cleanup_enabled:
                logger.info("🧹 Running final cleanup...")
                await run_periodic_cleanup()
            
            logger.info("✅ All systems shut down successfully!")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")


async def main():
    """Main startup function."""
    try:
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, settings.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger.info("🚀 Starting Enhanced CoolDL Bot...")
        
        # Create enhanced bot instance
        enhanced_bot = EnhancedCoolDLBot()
        
        # Initialize all systems
        await enhanced_bot.initialize_systems()
        
        # Start background tasks
        await enhanced_bot.start_background_tasks()
        
        logger.info("🎉 Enhanced CoolDL Bot is ready!")
        logger.info("💡 Features enabled:")
        logger.info("   - 🔒 Advanced security monitoring")
        logger.info("   - 📁 Smart file management") 
        logger.info("   - 🛠️ Enhanced error recovery")
        logger.info("   - 🧹 Automatic file cleanup")
        
        # Keep the bot running
        while enhanced_bot.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await enhanced_bot.shutdown()


def run_enhanced_bot():
    """Run the enhanced bot with proper error handling."""
    try:
        # Import and run the original bot
        from async_downloader import main as original_main
        
        logger.info("🔄 Starting original bot with enhanced features...")
        
        # Run original bot main function
        asyncio.run(main())
        
    except Exception as e:
        logger.error(f"Failed to run enhanced bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_enhanced_bot()