"""
STEP File Upload Watcher Service

Monitors the PDM_Upload folder for new STEP files and intelligently
uploads them to the PDM system:

- Compares against stored fingerprint (fast - no download needed)
- Skips identical files
- Uploads changed files with automatic rev bump
- Logs all actions for review

Usage:
    python -m app.services.step_upload_watcher [--watch] [--once]

    --watch: Continuously monitor folder for new files
    --once:  Process all files in folder once and exit (default)
"""

import os
import re
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from .step_compare import parse_step_file, parse_step_fingerprint, StepFingerprint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of processing a single file."""
    filename: str
    item_number: str
    action: str  # 'skipped', 'uploaded', 'error', 'new_item'
    message: str
    old_rev: Optional[str] = None
    new_rev: Optional[str] = None
    differences: Optional[dict] = None


def get_next_rev(current_rev: str) -> str:
    """Increment revision letter: A->B, B->C, etc."""
    if not current_rev:
        return 'A'
    # Handle single letter revs
    if len(current_rev) == 1 and current_rev.isalpha():
        if current_rev.upper() == 'Z':
            return 'AA'
        return chr(ord(current_rev.upper()) + 1)
    return current_rev + '.1'  # Fallback


def extract_item_number(filename: str) -> Optional[str]:
    """Extract item number from filename like csp00110.step or csp00110_A.step."""
    match = re.match(r'^([a-z]{3}\d+)', filename.lower())
    return match.group(1) if match else None


class StepUploadWatcher:
    """Watches a folder for STEP files and uploads them to PDM."""

    def __init__(self, upload_folder: str, supabase_client=None):
        self.upload_folder = Path(upload_folder)
        self.supabase = supabase_client
        self.processed_folder = self.upload_folder / "processed"
        self.skipped_folder = self.upload_folder / "skipped"
        self.error_folder = self.upload_folder / "errors"

        # Create subfolders
        for folder in [self.processed_folder, self.skipped_folder, self.error_folder]:
            folder.mkdir(exist_ok=True)

    def _get_supabase(self):
        """Lazy load Supabase client."""
        if self.supabase is None:
            from .supabase import get_supabase_admin
            self.supabase = get_supabase_admin()
        return self.supabase

    def get_stored_fingerprint(self, item_number: str) -> tuple[Optional[dict], Optional[dict]]:
        """
        Get stored fingerprint for an item's STEP file.

        Returns:
            (fingerprint_dict, file_record) or (None, None) if not found
        """
        supabase = self._get_supabase()

        # Get item
        item_result = supabase.table("items").select("id, revision").eq(
            "item_number", item_number
        ).execute()

        if not item_result.data:
            return None, None

        item_id = item_result.data[0]["id"]
        item_rev = item_result.data[0].get("revision", "A")

        # Get STEP file with fingerprint
        file_result = supabase.table("files").select(
            "id, file_path, file_name, step_fingerprint, revision"
        ).eq("item_id", item_id).or_(
            "file_type.eq.STP,file_type.eq.STEP"
        ).execute()

        if not file_result.data:
            return None, {"item_id": item_id, "item_rev": item_rev}

        file_record = file_result.data[0]
        file_record["item_id"] = item_id
        file_record["item_rev"] = item_rev

        return file_record.get("step_fingerprint"), file_record

    def download_and_fingerprint(self, file_path: str) -> Optional[StepFingerprint]:
        """Download a file from storage and compute its fingerprint."""
        supabase = self._get_supabase()

        parts = file_path.split("/", 1)
        if len(parts) == 2:
            bucket, storage_path = parts
        else:
            bucket, storage_path = "pdm-files", file_path

        try:
            content = supabase.storage.from_(bucket).download(storage_path)
            return parse_step_fingerprint(content)
        except Exception as e:
            logger.error(f"Could not download {file_path}: {e}")
            return None

    def upload_step_file(
        self,
        local_path: Path,
        item_number: str,
        item_id: str,
        new_rev: str,
        fingerprint: StepFingerprint
    ) -> bool:
        """Upload a STEP file to PDM storage and update database."""
        supabase = self._get_supabase()

        bucket = "pdm-files"
        storage_path = f"{item_number}/{item_number}.step"
        full_path = f"{bucket}/{storage_path}"

        try:
            # Read file content
            content = local_path.read_bytes()

            # Upload to storage (update if exists)
            try:
                supabase.storage.from_(bucket).upload(
                    storage_path, content,
                    file_options={"content-type": "application/octet-stream"}
                )
            except Exception:
                # File exists, update it
                supabase.storage.from_(bucket).update(
                    storage_path, content,
                    file_options={"content-type": "application/octet-stream"}
                )

            # Update or create file record
            file_result = supabase.table("files").select("id").eq(
                "item_id", item_id
            ).or_("file_type.eq.STP,file_type.eq.STEP").execute()

            file_data = {
                "file_path": full_path,
                "file_name": f"{item_number}.step",
                "file_type": "STP",
                "file_size": len(content),
                "revision": new_rev,
                "step_fingerprint": fingerprint.to_dict(),
                "updated_at": datetime.utcnow().isoformat()
            }

            if file_result.data:
                # Update existing
                supabase.table("files").update(file_data).eq(
                    "id", file_result.data[0]["id"]
                ).execute()
            else:
                # Create new
                file_data["item_id"] = item_id
                file_data["iteration"] = 1
                supabase.table("files").insert(file_data).execute()

            # Update item revision
            supabase.table("items").update({
                "revision": new_rev,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", item_id).execute()

            return True

        except Exception as e:
            logger.error(f"Upload failed for {item_number}: {e}")
            return False

    def process_file(self, file_path: Path) -> UploadResult:
        """Process a single STEP file."""
        filename = file_path.name
        item_number = extract_item_number(filename)

        if not item_number:
            return UploadResult(
                filename=filename,
                item_number="",
                action="error",
                message=f"Could not extract item number from {filename}"
            )

        logger.info(f"Processing {filename} -> {item_number}")

        # Compute fingerprint of new file
        try:
            new_fp = parse_step_file(file_path)
        except Exception as e:
            return UploadResult(
                filename=filename,
                item_number=item_number,
                action="error",
                message=f"Could not parse STEP file: {e}"
            )

        # Get stored fingerprint
        stored_fp_dict, file_record = self.get_stored_fingerprint(item_number)

        if file_record is None:
            return UploadResult(
                filename=filename,
                item_number=item_number,
                action="error",
                message=f"Item {item_number} not found in PDM"
            )

        item_id = file_record["item_id"]
        current_rev = file_record.get("item_rev", "A")

        # If no existing file, upload as new
        if stored_fp_dict is None and file_record.get("file_path") is None:
            new_rev = current_rev or "A"
            if self.upload_step_file(file_path, item_number, item_id, new_rev, new_fp):
                return UploadResult(
                    filename=filename,
                    item_number=item_number,
                    action="uploaded",
                    message=f"New STEP file uploaded as Rev {new_rev}",
                    new_rev=new_rev
                )
            else:
                return UploadResult(
                    filename=filename,
                    item_number=item_number,
                    action="error",
                    message="Upload failed"
                )

        # Compare fingerprints
        if stored_fp_dict:
            # Reconstruct StepFingerprint from stored dict
            stored_fp = StepFingerprint()
            entity_counts = stored_fp_dict.get("entity_counts", {})
            stored_fp.cartesian_points = entity_counts.get("cartesian_points", 0)
            stored_fp.directions = entity_counts.get("directions", 0)
            stored_fp.vectors = entity_counts.get("vectors", 0)
            stored_fp.lines = entity_counts.get("lines", 0)
            stored_fp.circles = entity_counts.get("circles", 0)
            stored_fp.planes = entity_counts.get("planes", 0)
            stored_fp.advanced_faces = entity_counts.get("advanced_faces", 0)
            stored_fp.closed_shells = entity_counts.get("closed_shells", 0)
            stored_fp.manifold_solids = entity_counts.get("manifold_solids", 0)
            stored_fp.total_entities = entity_counts.get("total", 0)

            bbox = stored_fp_dict.get("bounding_box", {})
            mins = bbox.get("min", [0, 0, 0])
            maxs = bbox.get("max", [0, 0, 0])
            stored_fp.min_x, stored_fp.min_y, stored_fp.min_z = mins
            stored_fp.max_x, stored_fp.max_y, stored_fp.max_z = maxs

            is_match = stored_fp.matches(new_fp)
            differences = stored_fp.diff(new_fp)
        else:
            # No stored fingerprint, need to download and compare
            logger.info(f"  No cached fingerprint, downloading existing file...")
            existing_fp = self.download_and_fingerprint(file_record["file_path"])
            if existing_fp:
                is_match = existing_fp.matches(new_fp)
                differences = existing_fp.diff(new_fp)
                # Store fingerprint for future
                self._get_supabase().table("files").update({
                    "step_fingerprint": existing_fp.to_dict()
                }).eq("id", file_record["id"]).execute()
            else:
                is_match = False
                differences = {"error": "Could not compare"}

        if is_match:
            return UploadResult(
                filename=filename,
                item_number=item_number,
                action="skipped",
                message=f"File matches stored version (Rev {current_rev})",
                old_rev=current_rev
            )
        else:
            # Upload with rev bump
            new_rev = get_next_rev(current_rev)
            if self.upload_step_file(file_path, item_number, item_id, new_rev, new_fp):
                return UploadResult(
                    filename=filename,
                    item_number=item_number,
                    action="uploaded",
                    message=f"File changed, uploaded as Rev {new_rev}",
                    old_rev=current_rev,
                    new_rev=new_rev,
                    differences=differences
                )
            else:
                return UploadResult(
                    filename=filename,
                    item_number=item_number,
                    action="error",
                    message="Upload failed"
                )

    def move_file(self, file_path: Path, result: UploadResult):
        """Move file to appropriate subfolder based on result."""
        if result.action == "skipped":
            dest = self.skipped_folder / file_path.name
        elif result.action == "uploaded":
            dest = self.processed_folder / file_path.name
        else:
            dest = self.error_folder / file_path.name

        # Add timestamp to avoid overwrites
        if dest.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest.with_name(f"{dest.stem}_{timestamp}{dest.suffix}")

        file_path.rename(dest)
        logger.info(f"  Moved to {dest.parent.name}/")

    def process_folder(self) -> list[UploadResult]:
        """Process all STEP files in the upload folder."""
        results = []

        # Collect STEP files, deduplicating for case-insensitive file systems
        seen_files = set()
        step_files = []
        for pattern in ["*.step", "*.stp", "*.STEP", "*.STP"]:
            for f in self.upload_folder.glob(pattern):
                key = f.name.lower()
                if key not in seen_files:
                    seen_files.add(key)
                    step_files.append(f)

        if not step_files:
            logger.info("No STEP files found in upload folder")
            return results

        logger.info(f"Found {len(step_files)} STEP file(s) to process")

        for file_path in step_files:
            result = self.process_file(file_path)
            results.append(result)

            # Log result
            if result.action == "skipped":
                logger.info(f"  SKIPPED: {result.message}")
            elif result.action == "uploaded":
                logger.info(f"  UPLOADED: {result.message}")
                if result.differences:
                    logger.info(f"    Changes: {list(result.differences.keys())}")
            else:
                logger.warning(f"  ERROR: {result.message}")

            # Move file
            self.move_file(file_path, result)

        # Summary
        skipped = sum(1 for r in results if r.action == "skipped")
        uploaded = sum(1 for r in results if r.action == "uploaded")
        errors = sum(1 for r in results if r.action == "error")
        logger.info(f"\nSummary: {uploaded} uploaded, {skipped} skipped, {errors} errors")

        return results

    def watch(self, poll_interval: int = 5):
        """Continuously watch folder for new files."""
        logger.info(f"Watching {self.upload_folder} for new STEP files...")
        logger.info("Press Ctrl+C to stop")

        try:
            while True:
                self.process_folder()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Stopped watching")


def process_upload_folder(folder_path: str = None) -> list[UploadResult]:
    """
    Process all STEP files in the upload folder.

    Default folder: J:/PDM-Web/PDM_Upload
    """
    if folder_path is None:
        folder_path = "J:/PDM-Web/PDM_Upload"

    # Create folder if it doesn't exist
    Path(folder_path).mkdir(exist_ok=True)

    watcher = StepUploadWatcher(folder_path)
    return watcher.process_folder()


if __name__ == "__main__":
    import sys

    upload_folder = "J:/PDM-Web/PDM_Upload"

    if "--watch" in sys.argv:
        watcher = StepUploadWatcher(upload_folder)
        watcher.watch()
    else:
        results = process_upload_folder(upload_folder)

        # Print summary
        print("\n" + "=" * 60)
        print("UPLOAD RESULTS")
        print("=" * 60)
        for r in results:
            status = "[+]" if r.action == "uploaded" else "[=]" if r.action == "skipped" else "[!]"
            print(f"{status} {r.item_number}: {r.action.upper()} - {r.message}")
