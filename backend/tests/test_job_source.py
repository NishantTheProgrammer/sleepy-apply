from app.sources.static_urls import StaticUrlJobSource
from app.sources.base import RawJobData


def test_content_hash_deduplication():
    source = StaticUrlJobSource()
    job1 = RawJobData(
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        source_url="https://example.com/jobs/1",
        description="Build scalable APIs with Python.",
    )
    job2 = RawJobData(
        title="  Software Engineer ",
        company="acme corp",
        location="REMOTE ",
        source_url="https://different-source.com/jobs/99",
        description="Different description, but same role and company.",
    )

    hash1 = source.get_content_hash(job1)
    hash2 = source.get_content_hash(job2)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 length
