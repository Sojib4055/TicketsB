from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DHAKA = ZoneInfo('Asia/Dhaka')
TERMINAL = {'CONFIRMED', 'CANCELLED', 'EXPIRED'}
MONITORED = {'SCHEDULED', 'MONITORING'}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Passenger(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    gender: Literal['male', 'female']


class BusSearch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    from_city: str = Field(min_length=2, max_length=60)
    to_city: str = Field(min_length=2, max_length=60)
    journey_date: date
    seat_count: int = Field(default=1, ge=1, le=4)

    @model_validator(mode='after')
    def valid_route(self):
        if self.from_city.casefold() == self.to_city.casefold():
            raise ValueError('Choose a different destination')
        today = utcnow().astimezone(DHAKA).date()
        if not today <= self.journey_date <= today + timedelta(days=90):
            raise ValueError('Choose a journey date within the next 90 days')
        return self


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    from_city: str = Field(min_length=2, max_length=60)
    to_city: str = Field(min_length=2, max_length=60)
    journey_date: date
    departure_start: time = time(0, 0)
    departure_end: time = time(23, 59)
    buy_after: datetime
    buy_before: datetime
    max_total: Decimal = Field(gt=0, le=100000, max_digits=8, decimal_places=2)
    seat_count: int = Field(ge=1, le=4)
    seat_preference: Literal['any', 'window', 'aisle', 'front', 'middle'] = 'any'
    operators: list[str] = Field(default_factory=list, max_length=10)
    boarding_point: str = Field(default='', max_length=120)
    contact_phone: str
    contact_email: str = Field(max_length=120)
    whatsapp_phone: str = ''
    whatsapp_opt_in: bool = False
    low_seat_threshold: int = Field(default=5, ge=1, le=40)
    passengers: list[Passenger] = Field(min_length=1, max_length=4)
    selected_offer_id: str = Field(default='', max_length=100)
    preferred_seats: list[str] = Field(default_factory=list, max_length=4)
    monitor_only: bool = False
    seat_fallback: Literal['wait', 'any'] = 'wait'
    # Stable client-generated key prevents a repeated submit from creating two jobs.
    request_key: str = Field(default='', max_length=100, pattern=r'^[A-Za-z0-9_-]*$')

    @field_validator('contact_phone', 'whatsapp_phone')
    @classmethod
    def phone(cls, value: str, info):
        import re
        value = re.sub(r'[\s()-]', '', value)
        if not value and info.field_name == 'whatsapp_phone':
            return value
        if not re.fullmatch(r'\+[1-9]\d{7,14}', value):
            raise ValueError('Use an international phone number, for example +8801712345678')
        return value

    @field_validator('contact_email')
    @classmethod
    def email(cls, value: str):
        import re
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid contact email')
        return value.lower()

    @field_validator('buy_after', 'buy_before')
    @classmethod
    def aware(cls, value: datetime):
        return (value.replace(tzinfo=DHAKA) if value.tzinfo is None else value).astimezone(timezone.utc)

    @model_validator(mode='after')
    def coherent(self):
        if self.from_city.casefold() == self.to_city.casefold():
            raise ValueError('Origin and destination must be different')
        if self.buy_before <= self.buy_after:
            raise ValueError('The buying window must end after it starts')
        if self.buy_before.astimezone(DHAKA).date() > self.journey_date:
            raise ValueError('The buying window cannot end after the journey date')
        if len(self.passengers) != self.seat_count:
            raise ValueError('Add passenger details for every requested seat')
        if self.whatsapp_opt_in and not self.whatsapp_phone:
            raise ValueError('A WhatsApp number is required for alerts')
        if self.preferred_seats and (len(self.preferred_seats) != self.seat_count or len(set(self.preferred_seats)) != self.seat_count):
            raise ValueError('Select a different seat for each passenger')
        if self.preferred_seats and not self.selected_offer_id:
            raise ValueError('Specific seats require a selected departure')
        if any(not seat.strip() or len(seat) > 20 for seat in self.preferred_seats):
            raise ValueError('Invalid seat label')
        if self.departure_start == self.departure_end:
            departure = datetime.combine(self.journey_date, self.departure_start, DHAKA)
            if self.buy_before > departure:
                raise ValueError('Your time window must end before the selected departure')
        return self

    def validate_new(self, now: datetime | None = None):
        now = now or utcnow()
        if self.buy_before <= now or self.journey_date < now.astimezone(DHAKA).date():
            raise ValueError('Choose a future journey and a buying window that has not ended')


class BusOffer(BaseModel):
    id: str
    operator: str
    route: str
    departure: str
    arrival: str = ''
    unit_fare: Decimal = Field(gt=0)
    seats_available: int = Field(ge=0)
    currency: str = 'BDT'
    service_class: str = ''
    duration: str = ''
    boarding_points: list[str] = Field(default_factory=list)
    dropping_points: list[str] = Field(default_factory=list)
    provider_note: str = ''

    def total(self, request: BookingRequest) -> Decimal:
        return self.unit_fare * request.seat_count

    def departure_at(self, request: BookingRequest) -> datetime | None:
        for fmt in ('%I:%M %p', '%H:%M'):
            try:
                value = datetime.strptime(self.departure.strip(), fmt).time()
                return datetime.combine(request.journey_date, value, DHAKA)
            except ValueError:
                pass
        return None

    def relevant(self, request: BookingRequest) -> bool:
        """Identity/time match, independent of price and remaining quantity."""
        if request.selected_offer_id and self.id != request.selected_offer_id:
            return False
        if request.operators and not any(o.casefold() in self.operator.casefold() for o in request.operators):
            return False
        departure = None
        for fmt in ('%I:%M %p', '%H:%M'):
            try:
                departure = datetime.strptime(self.departure.strip(), fmt).time()
                break
            except ValueError:
                continue
        if departure is None:
            return False
        start, end = request.departure_start, request.departure_end
        return start <= departure <= end if start <= end else departure >= start or departure <= end

    def matches(self, request: BookingRequest) -> bool:
        return (self.relevant(request) and self.currency == 'BDT' and
                self.seats_available >= request.seat_count and self.total(request) <= request.max_total)


class NeedsAttention(RuntimeError):
    """A provider step cannot safely be completed automatically."""


class ProviderBusy(RuntimeError):
    """Capacity exhaustion is retryable and must not count as a booking failure."""
