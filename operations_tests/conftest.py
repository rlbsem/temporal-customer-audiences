import pytest

from audience_ops.activation import Activation
from audience_ops.runtime import LocalRuntime
from audience_ops.scenario import actor, seed
from temporal_audiences.fixtures import BASE, DAY


@pytest.fixture
def runtime(tmp_path):
    with LocalRuntime(tmp_path / "runtime") as environment:
        yield environment


@pytest.fixture
def primed(runtime):
    runtime.ops = seed(runtime.config)
    for brand in ["atlas", "nova"]:
        runtime.ops.publish(actor("controller"), brand, "baseline", BASE + 3 * DAY)
    runtime.activation = Activation(runtime.config["dsn"], runtime.client)
    return runtime


def approved(runtime, person="400", brand="atlas", segment="engaged_trial"):
    row = runtime.activation.plan(actor("controller"), brand, person, segment, True)
    runtime.activation.approve(actor("approver"), brand, row["id"], row["hash"])
    return row
