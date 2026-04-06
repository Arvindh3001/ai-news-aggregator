"""
Entry point for the AI News Aggregator.

Invoked directly by the Render cron job:
    python main.py

Also works locally:
    python -m uv run python main.py
"""
import logging
import sys


def _configure_logging() -> None:
    """
    Set up root logger:
      - INFO and above → stdout (structured line format with timestamp)
      - Suppress noisy third-party loggers to WARNING
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Suppress chatty third-party loggers
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    _configure_logging()

    logger = logging.getLogger(__name__)
    logger.info("AI News Aggregator starting up.")

    # Import here (after logging is configured) so module-level loggers
    # in the app pick up the root handler we just installed.
    from app.services.pipeline import run_pipeline

    run_pipeline()

    logger.info("Done.")


if __name__ == "__main__":
    main()
