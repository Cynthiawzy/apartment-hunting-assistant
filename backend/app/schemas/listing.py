from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.listing import ListingStatus, SourceSite


class ListingBase(BaseModel):
    source_site: SourceSite
    source_listing_id: str
    url: str
    address_line: str
    unit: str | None = None
    city: str
    state: str = Field(min_length=2, max_length=2)
    zip_code: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    price: float = Field(gt=0)
    bedrooms: float = Field(ge=0)
    bathrooms: float = Field(ge=0)
    sqft: int | None = Field(default=None, gt=0)
    available_date: date | None = None
    pet_friendly: bool | None = None
    amenities: list[str] | None = None
    landlord_name: str | None = None
    landlord_phone: str | None = None
    landlord_email: str | None = None
    description: str | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    scraped_at: date
    neighborhood_id: int | None = None


class ListingCreate(ListingBase):
    pass


class ListingResponse(ListingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    distance_km: float | None = None
    created_at: datetime
    updated_at: datetime


class ListingFilter(BaseModel):
    budget_max: float | None = Field(default=None, gt=0)
    min_beds: float | None = Field(default=None, ge=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def _geo_params_together(self) -> "ListingFilter":
        geo = (self.latitude, self.longitude, self.radius_km)
        if any(v is not None for v in geo) and not all(v is not None for v in geo):
            raise ValueError("latitude, longitude, and radius_km must be provided together")
        return self
