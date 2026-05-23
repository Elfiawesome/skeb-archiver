import logging
import sys
from typing import Optional

_CONFIGURED = False

def get_logger(
	name: str = "skeb",
	level: int = logging.INFO,
	log_file: Optional[str] = None,
) -> logging.Logger:
	global _CONFIGURED
	logger = logging.getLogger(name)

	if _CONFIGURED:
		return logger

	logger.setLevel(level)

	fmt = logging.Formatter(
		fmt="%(asctime)s | %(levelname)-8s | %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)

	console = logging.StreamHandler(sys.stdout)
	console.setFormatter(fmt)
	logger.addHandler(console)

	if log_file:
		fh = logging.FileHandler(log_file, encoding="utf-8")
		fh.setFormatter(fmt)
		logger.addHandler(fh)

	_CONFIGURED = True
	return logger


log = get_logger()