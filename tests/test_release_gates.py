from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, check=True)


def test_installer_and_operational_scripts_are_valid_bash() -> None:
    scripts = [
        ROOT / "deploy/install.sh",
        ROOT / "deploy/scripts/backup.sh",
        ROOT / "deploy/scripts/native-backup.sh",
        ROOT / "deploy/scripts/native-restore.sh",
        ROOT / "deploy/scripts/rollback.sh",
    ]
    for script in scripts:
        run("bash", "-n", str(script))


def test_native_backup_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "pars2ray.db"
    out = tmp_path / "backups"
    etc = tmp_path / "etc"
    etc.mkdir()
    env_file = etc / "pars2ray.env"
    database_url = f"sqlite:////{db}"
    env_file.write_text(f"DATABASE_URL={database_url}\n", encoding="utf-8")
    with sqlite3.connect(db) as conn:
        conn.execute("create table marker (value text not null)")
        conn.execute("insert into marker values ('before-backup')")
        conn.commit()
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.update({
        "PARS2RAY_ETC_DIR": str(etc),
        "PARS2RAY_BACKUP_DIR": str(out),
    })
    result = run("bash", "deploy/scripts/native-backup.sh", env=env)
    backup = Path(result.stdout.strip().splitlines()[-1])
    assert backup.exists()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("select value from marker").fetchone() == ("before-backup",)


def test_rollback_is_guarded() -> None:
    script = (ROOT / "deploy/scripts/rollback.sh").read_text(encoding="utf-8")
    assert "working tree is dirty; refusing rollback" in script
    assert "rev-parse --verify" in script
    assert "systemctl restart pars2ray-master pars2ray-worker" in script


def test_installer_upgrade_preserves_existing_credentials() -> None:
    installer = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
    assert 'Existing installation detected; keeping panel credentials and settings' in installer
    assert 'set_env ADMIN_PASSWORD' in installer
    assert 'git -C "$INSTALL_DIR" reset --hard "origin/$REF"' in installer


def test_migration_configuration_is_present() -> None:
    assert (ROOT / "alembic.ini").is_file()
    assert (ROOT / "migrations" / "env.py").is_file()
    versions = ROOT / "migrations" / "versions"
    assert versions.is_dir()
    assert list(versions.glob("*.py")), "migration versions are missing"
