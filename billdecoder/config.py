"""Central configuration. Everything reads from here, nothing else touches os.environ."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")
CACHE_DIR = ROOT / ".cache"
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "4"))
MAX_IMAGE_SIDE = 2600          # px; larger images are downscaled before upload
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
FEWSHOT_BILL = ROOT / "train" / "bills" / "KESC_0008.png"
FEWSHOT_GOLD = ROOT / "eval" / "gold" / "KESC_0008.json"
