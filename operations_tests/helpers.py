from audience_ops.scenario import actor


def approved(runtime, person="400", brand="atlas", segment="engaged_trial"):
    row = runtime.activation.plan(actor("controller"), brand, person, segment, True)
    runtime.activation.approve(actor("approver"), brand, row["id"], row["hash"])
    return row
