import csv

from dev_support.instructor_jobs import REQUIRED_COLUMNS, import_jobs, load_jobs


def test_historical_import_filters_and_preserves_balance(tmp_path, world):
    source = tmp_path / "archive.csv"
    row = {
        "Job Title": "Build a dashboard", "Description": "Summarize sales",
        "Job_URL": "https://example.test/job/1", "Payment_type": "Fixed-price",
        "Job_Cost": "$1,200.00", "New_Connects_Num": "8", "Category_1": "Python",
    }
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows([row, row, {**row, "Payment_type": "Hourly"},
                          {**row, "Job_URL": "other", "Job_Cost": ""}])

    job, = load_jobs(source, 10)
    marketplace, tenant, _ = world
    balance = marketplace.balance(tenant)
    import_jobs(tenant, [job])
    import_jobs(tenant, [job])

    assert marketplace.job(tenant, job.id) == job
    assert job.budget == 1200
    assert marketplace.client_history(tenant, job.client_id)["synthetic"]
    assert marketplace.balance(tenant) == balance
