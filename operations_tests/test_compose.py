from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_bounds_exposure_and_separates_runtime_credentials():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["console"]["ports"] == ["127.0.0.1:8596:8596"]
    assert all("ports" not in s for n, s in services.items() if n != "console")
    assert compose["networks"]["isolated"]["internal"]
    assert services["console"]["networks"] == ["isolated", "console_access"]
    assert all(s["networks"] == ["isolated"] for n, s in services.items() if n != "console")
    assert compose["networks"]["console_access"]["driver_opts"]["com.docker.network.bridge.host_binding_ipv4"] == "127.0.0.1"
    for name in ["receiver", "demo", "console"]:
        assert services[name]["read_only"] and services[name]["cap_drop"] == ["ALL"]
        assert services[name]["tmpfs"] == ["/tmp:size=128m,mode=1777"]
    assert services["console"]["volumes"] == ["console-config:/console:ro"]
    assert services["receiver"]["volumes"] == ["receiver-config:/receiver:ro"]
    assert not any("PASSWORD" in k for k in services["postgres"]["environment"] if k != "POSTGRES_PASSWORD_FILE")


def test_runtime_container_has_no_privileged_user_or_unreviewed_build_context():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in docker and "COPY . " not in docker
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert all(n in ignored for n in [".git", ".venv", "work", ".env"])
