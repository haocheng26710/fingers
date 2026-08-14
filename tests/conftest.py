from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_PACKAGE = (
    REPO_ROOT
    / "reference"
    / "model_packages"
    / "Acoustic_Ladder_V1_3_calibrated_round_main_tube_print_package.zip"
)
CALIBRATION_RECORD = REPO_ROOT / "reference" / "calibration" / "V1_3_user_calibration_record.json"
MANIFEST_SCHEMA = REPO_ROOT / "schemas" / "device_manifest.schema.json"
