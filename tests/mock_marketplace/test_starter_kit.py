from dev_support.starter_kit import seed


def test_import_starter_kit_is_repeatable(world):
    marketplace, tenant, _ = world
    balance = marketplace.balance(tenant)

    seed(tenant)
    seed(tenant)

    job = marketplace.job(tenant, "sample-job-001")
    assert job.budget == 450
    assert job.connects == 8
    assert marketplace.client_history(tenant, job.client_id)["verified"] is False
    assert marketplace.job(tenant, "sample-job-002").budget == 0
    assert marketplace.balance(tenant) == balance
