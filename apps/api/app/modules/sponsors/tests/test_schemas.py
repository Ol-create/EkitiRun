import pytest
from pydantic import ValidationError

from app.modules.sponsors.schemas import (
    SponsorTierCreate,
    SponsorTierResponse,
    SponsorTierUpdate,
)


def test_create_sponsor_tier_with_valid_data():
    tier = SponsorTierCreate(
        name="Gold",
        amount_kobo=500000,
        benefits=["Logo placement", "Social media promotion"],
        sort_order=1,
    )

    assert tier.name == "Gold"
    assert tier.amount_kobo == 500000
    assert len(tier.benefits) == 2


def test_create_sponsor_tier_rejects_zero_amount():
    with pytest.raises(ValidationError):
        SponsorTierCreate(
            name="Gold",
            amount_kobo=0,
            benefits=["Logo placement"],
        )


def test_create_sponsor_tier_rejects_empty_benefits():
    with pytest.raises(ValidationError):
        SponsorTierCreate(
            name="Gold",
            amount_kobo=500000,
            benefits=[],
        )


def test_update_sponsor_tier_allows_partial_data():
    update = SponsorTierUpdate(name="Platinum")

    assert update.name == "Platinum"
    assert update.model_dump(exclude_unset=True) == {
        "name": "Platinum"
    }


def test_sponsor_tier_response_includes_id():
    tier = SponsorTierResponse(
        id=1,
        name="Gold",
        amount_kobo=500000,
        benefits=["Logo placement"],
        sort_order=1,
    )

    assert tier.id == 1
