from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_auto_update_artifacts_exist():
    assert (ROOT / "deploy/scripts/auto-update.sh").is_file()
    assert (ROOT / "deploy/systemd/pars2ray-auto-update.service").is_file()
    assert (ROOT / "deploy/systemd/pars2ray-auto-update.timer").is_file()


def test_auto_update_is_transactional_and_opt_out():
    script = (ROOT / "deploy/scripts/auto-update.sh").read_text()
    assert 'PARS2RAY_AUTO_UPDATE_ENABLED:-1' in script
    assert 'git status --porcelain' in script
    assert 'git reset --hard "$BACKUP_REF"' in script
    assert 'systemctl restart pars2ray-master.service pars2ray-worker.service' in script
    assert 'health check failed after update' in script


def test_installed_cli_enables_timer():
    cli = (ROOT / "deploy/pars2ray").read_text()
    assert 'pars2ray-auto-update.timer' in cli
    assert 'systemctl enable --now pars2ray-auto-update.timer' in cli
    assert 'PARS2RAY_AUTO_UPDATE_ENABLED:-1' in cli
