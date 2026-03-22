import asyncio
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from main import run_scraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s'
)
logger = logging.getLogger(__name__)


def job():
    logger.info("Scheduler: starting scraper run...")
    new, updated = asyncio.run(run_scraper())
    logger.info(f"Scheduler: run complete. New={new}, Updated={updated}")


if __name__ == '__main__':
    scheduler = BlockingScheduler(timezone='Europe/Istanbul')
    # Her gece 03:00 (Istanbul time)
    scheduler.add_job(job, CronTrigger(hour=3, minute=0))
    logger.info("Scheduler started. Next run at 03:00 Istanbul time.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
