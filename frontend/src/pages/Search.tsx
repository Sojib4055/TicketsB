import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowDownUp,
  ArrowRight,
  ArrowUpRight,
  Bell,
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Compass,
  Filter,
  MapPin,
  MessageCircle,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Ticket,
  Users,
  X,
} from "lucide-react";
import { useApp } from "../lib/context";
import {
  api,
  busType,
  dateLabel,
  dateOffset,
  minutes,
  money,
  today,
  when,
} from "../lib/api";
import type { Offer, SearchInput, SearchResult, SeatMap } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, Spinner } from "../components/ui";
import { DestinationArt, RoadIllustration } from "../components/Scenery";

const cities = [
  "Dhaka",
  "Bogura",
  "Chattogram",
  "Cox's Bazar",
  "Sylhet",
  "Rajshahi",
  "Khulna",
  "Rangpur",
  "Barishal",
  "Dinajpur",
];
const initialQuery = (): SearchInput => ({
  from_city: "Dhaka",
  to_city: "Bogura",
  journey_date: dateOffset(1),
  seat_count: 1,
});
const defaults = {
  type: "",
  operator: "",
  time: "",
  boarding: "",
  fare: 100000,
  sort: "fare",
};
export default function SearchPage() {
  const app = useApp();
  const [query, setQuery] = useState(initialQuery);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [filters, setFilters] = useState(defaults);
  const [mobileFilters, setMobileFilters] = useState(false);
  const [seatOffer, setSeatOffer] = useState<Offer | null>(null);
  const [limit, setLimit] = useState(20);
  const resultRef = useRef<HTMLDivElement>(null);
  const search = useMutation({
    mutationFn: (input: SearchInput) => api<SearchResult>("/api/search", input),
    onSuccess: (data) => {
      setResult(data);
      setFilters(defaults);
      setLimit(20);
      window.setTimeout(
        () =>
          resultRef.current?.scrollIntoView({
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
              .matches
              ? "instant"
              : "smooth",
            block: "start",
          }),
        100,
      );
    },
    onError: () => setResult(null),
  });
  const run = (input = query) => {
    if (!search.isPending) {
      setQuery(input);
      setSeatOffer(null);
      search.mutate(input);
    }
  };
  const filtered = useMemo(
    () =>
      (result?.offers || [])
        .filter(
          (o) =>
            (!filters.type || busType(o.service_class) === filters.type) &&
            (!filters.operator || o.operator === filters.operator) &&
            (!filters.boarding ||
              o.boarding_points.includes(filters.boarding)) &&
            (!filters.time ||
              Math.floor(minutes(o.departure) / 360) ===
                Number(filters.time)) &&
            Number(o.unit_fare) <= filters.fare,
        )
        .sort((a, b) =>
          filters.sort === "departure"
            ? minutes(a.departure) - minutes(b.departure)
            : filters.sort === "seats"
              ? b.seats_available - a.seats_available
              : (Number(a.unit_fare) - Number(b.unit_fare)) *
                (filters.sort === "fare_desc" ? -1 : 1),
        ),
    [result, filters],
  );
  const activeFilters = [
    filters.type,
    filters.operator,
    filters.boarding,
    filters.time,
    filters.fare < 100000,
  ].filter(Boolean).length;
  function filter(key: keyof typeof defaults, value: string | number) {
    setFilters((f) => ({ ...f, [key]: value }));
    setLimit(20);
  }
  const maxFare = Math.max(
    100,
    ...(result?.offers || []).map((o) => Number(o.unit_fare)),
  );
  return (
    <div className="search-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">A BETTER WAY TO GET THERE</p>
          <h1>Where are we headed?</h1>
          <p>A seat for your plans. A little more peace of mind.</p>
        </div>
        <div className="heading-date">
          <CalendarDays size={17} />
          {dateLabel(today() + "T12:00:00+06:00", {
            weekday: "short",
            year: "numeric",
          })}
        </div>
      </div>
      <section className="search-hero">
        <div className="hero-copy">
          <span className="hero-tag">
            <span /> YOUR NEXT CHAPTER STARTS HERE
          </span>
          <h2>
            Great journeys begin
            <br />
            with <em>the right seat.</em>
          </h2>
          <p>
            Find your bus. Set your watch.
            <br />
            We’ll keep an eye on the journey ahead.
          </p>
          <div className="hero-benefits">
            <span>
              <Check size={13} /> Live availability
            </span>
            <span>
              <Check size={13} /> You control payment
            </span>
          </div>
        </div>
        <RoadIllustration />
      </section>
      <form
        className="search-form panel"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
        aria-label="Search buses"
      >
        <label>
          <span>
            <MapPin size={14} /> FROM
          </span>
          <input
            aria-label="Departure city"
            name="from_city"
            list="cities"
            minLength={2}
            maxLength={60}
            required
            value={query.from_city}
            onChange={(e) => setQuery({ ...query, from_city: e.target.value })}
          />
        </label>
        <button
          type="button"
          className="swap-button"
          aria-label="Swap origin and destination"
          onClick={() =>
            setQuery({
              ...query,
              from_city: query.to_city,
              to_city: query.from_city,
            })
          }
        >
          <ArrowDownUp size={17} />
        </button>
        <label>
          <span>
            <MapPin size={14} /> TO
          </span>
          <input
            aria-label="Destination city"
            name="to_city"
            list="cities"
            minLength={2}
            maxLength={60}
            required
            value={query.to_city}
            onChange={(e) => setQuery({ ...query, to_city: e.target.value })}
          />
        </label>
        <label>
          <span>
            <CalendarDays size={14} /> JOURNEY DATE
          </span>
          <input
            name="journey_date"
            aria-label="Journey date"
            type="date"
            min={today()}
            max={dateOffset(90)}
            required
            value={query.journey_date}
            onChange={(e) =>
              setQuery({ ...query, journey_date: e.target.value })
            }
          />
        </label>
        <label className="passenger-select">
          <span>
            <Users size={14} /> SEATS
          </span>
          <select
            aria-label="Number of seats"
            value={query.seat_count}
            onChange={(e) =>
              setQuery({ ...query, seat_count: Number(e.target.value) })
            }
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <button
          className="button primary search-submit"
          disabled={search.isPending}
        >
          {search.isPending ? (
            <Spinner label="Searching" />
          ) : (
            <>
              <Search size={18} /> Search buses
            </>
          )}
        </button>
        <datalist id="cities">
          {cities.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </datalist>
      </form>
      <div className="search-under">
        <span>
          <ShieldCheck size={14} /> Search freely. No account needed.
        </span>
        <span>
          Live inventory from <strong>Shohoz</strong>
          <span className="status-dot" />
        </span>
      </div>
      <ErrorBox error={search.error} />
      {app.config?.mode === "demo" && (
        <div className="mode-banner">
          <span className="mode-icon">
            <Sparkles size={15} />
          </span>
          <p>
            <strong>Live search, with you in control.</strong> Browse real
            departures and save availability watches. Automatic reservations are
            currently in demo mode.
          </p>
          <Badge tone="amber">Booking demo</Badge>
        </div>
      )}
      {search.isPending ? (
        <div className="search-skeleton" aria-live="polite">
          <Spinner label="Finding your next departure…" />
          <p>
            Checking current fares and seat availability with Shohoz. This can
            take up to a minute.
          </p>
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton-card">
              <div />
              <div />
              <div />
            </div>
          ))}
        </div>
      ) : result ? (
        <div ref={resultRef} className="results" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR OPTIONS, ALL IN ONE PLACE</p>
              <h2>
                {result.query.from_city} <ArrowRight size={20} />{" "}
                {result.query.to_city}
              </h2>
              <p>
                {dateLabel(result.query.journey_date + "T12:00:00+06:00", {
                  weekday: "long",
                  year: "numeric",
                })}{" "}
                · Updated {when(result.checked_at)}
              </p>
            </div>
            <Badge tone="green">Live departures</Badge>
          </div>
          <div className="date-strip">
            {[-1, 0, 1, 2, 3].map((offset) => {
              const value = dateOffset(offset, result.query.journey_date);
              return (
                <button
                  key={value}
                  className={offset === 0 ? "selected" : ""}
                  disabled={value < today() || value > dateOffset(90)}
                  onClick={() => run({ ...result.query, journey_date: value })}
                >
                  <span>
                    {dateLabel(value + "T12:00:00+06:00", { weekday: "short" })}
                  </span>
                  <small>
                    {offset === 0 ? "Selected date" : "View departures"}
                  </small>
                  {offset === 0 && <span className="date-dot" />}
                </button>
              );
            })}
          </div>
          <button
            className="button secondary mobile-filter-button"
            onClick={() => setMobileFilters(!mobileFilters)}
          >
            <Filter size={16} /> Filters{" "}
            {activeFilters > 0 && `(${activeFilters})`}
            <ChevronDown size={15} />
          </button>
          <div className="results-layout">
            <aside
              className={`filter-panel panel ${mobileFilters ? "expanded" : ""}`}
            >
              <div className="filter-header">
                <h3>
                  <SlidersHorizontal size={16} /> Filters
                </h3>
                <button
                  className="text-button"
                  onClick={() => {
                    setFilters(defaults);
                    setLimit(20);
                  }}
                >
                  Reset
                </button>
              </div>
              <fieldset>
                <legend>BUS TYPE</legend>
                {["AC", "Non AC"].map((type) => (
                  <label className="check-label" key={type}>
                    <input
                      type="checkbox"
                      checked={filters.type === type}
                      onChange={() =>
                        filter("type", filters.type === type ? "" : type)
                      }
                    />
                    {type}
                  </label>
                ))}
              </fieldset>
              <label className="filter-label">
                OPERATOR
                <select
                  aria-label="Filter by operator"
                  value={filters.operator}
                  onChange={(e) => filter("operator", e.target.value)}
                >
                  <option value="">All operators</option>
                  {[...new Set(result.offers.map((o) => o.operator))]
                    .sort()
                    .map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                </select>
              </label>
              <fieldset>
                <legend>DEPARTURE TIME</legend>
                {[
                  "Before 6 AM",
                  "6 AM – 12 PM",
                  "12 PM – 6 PM",
                  "After 6 PM",
                ].map((label, i) => (
                  <label className="check-label" key={label}>
                    <input
                      type="checkbox"
                      checked={filters.time === String(i)}
                      onChange={() =>
                        filter(
                          "time",
                          filters.time === String(i) ? "" : String(i),
                        )
                      }
                    />
                    <Clock3 size={13} />
                    {label}
                  </label>
                ))}
              </fieldset>
              <label className="filter-label">
                MAXIMUM FARE / SEAT
                <input
                  aria-label="Maximum fare per seat"
                  type="range"
                  min="0"
                  max={maxFare}
                  step="10"
                  value={Math.min(filters.fare, maxFare)}
                  onChange={(e) => filter("fare", Number(e.target.value))}
                />
                <span className="fare-range">
                  ৳ {money(Math.min(filters.fare, maxFare))}
                </span>
              </label>
              <label className="filter-label">
                BOARDING POINT
                <select
                  aria-label="Filter by boarding point"
                  value={filters.boarding}
                  onChange={(e) => filter("boarding", e.target.value)}
                >
                  <option value="">Any boarding point</option>
                  {[...new Set(result.offers.flatMap((o) => o.boarding_points))]
                    .sort()
                    .map((point) => (
                      <option key={point}>{point}</option>
                    ))}
                </select>
              </label>
              <div className="filter-note">
                <Bell size={18} />
                <strong>Not quite your time?</strong>
                <p>Watch a bus and let us check availability for you.</p>
              </div>
            </aside>
            <section className="bus-results">
              <div className="results-toolbar">
                <span>
                  <strong>{filtered.length}</strong> departures{" "}
                  {activeFilters > 0 && (
                    <button
                      className="filter-chip"
                      onClick={() => setFilters(defaults)}
                    >
                      {activeFilters} filters <X size={11} />
                    </button>
                  )}
                </span>
                <label>
                  Sort by{" "}
                  <select
                    aria-label="Sort departures"
                    value={filters.sort}
                    onChange={(e) => filter("sort", e.target.value)}
                  >
                    <option value="fare">Lowest fare</option>
                    <option value="fare_desc">Highest fare</option>
                    <option value="departure">Departure time</option>
                    <option value="seats">Most seats</option>
                  </select>
                </label>
              </div>
              {!filtered.length ? (
                <Empty
                  icon={<Search />}
                  title="A different route might be waiting."
                  action={
                    <button
                      className="button secondary"
                      onClick={() => setFilters(defaults)}
                    >
                      Reset filters
                    </button>
                  }
                >
                  No buses match your search. Try another date, route, or
                  filter.
                </Empty>
              ) : (
                filtered
                  .slice(0, limit)
                  .map((o) => (
                    <BusCard
                      key={o.id}
                      offer={o}
                      query={result.query}
                      onSeats={() => setSeatOffer(o)}
                      onWatch={() =>
                        app.plan({ offer: o, query: result.query, seats: [] })
                      }
                    />
                  ))
              )}
              {filtered.length > limit && (
                <button
                  className="button secondary load-more"
                  onClick={() => setLimit((n) => n + 20)}
                >
                  Show more departures <ChevronDown size={16} />
                  <span>{filtered.length - limit} more</span>
                </button>
              )}
            </section>
          </div>
        </div>
      ) : (
        <>
          <div className="overview-grid">
            <div className="overview-card">
              <span className="feature-icon purple">
                <Compass size={22} />
              </span>
              <div>
                <strong>Find your next stop</strong>
                <p>Live routes. Current fares.</p>
              </div>
              <ArrowUpRight size={17} />
            </div>
            <button className="overview-card" onClick={() => app.plan()}>
              <span className="feature-icon peach">
                <Ticket size={22} />
              </span>
              <div>
                <strong>
                  {app.jobs.length
                    ? `${app.jobs.length} saved journeys`
                    : "A plan that fits you"}
                </strong>
                <p>Set your time and budget.</p>
              </div>
              <ArrowUpRight size={17} />
            </button>
            <button className="overview-card" onClick={() => app.plan()}>
              <span className="feature-icon mint">
                <Bell size={22} />
              </span>
              <div>
                <strong>Stay one step ahead</strong>
                <p>Watch seats before they go.</p>
              </div>
              <ArrowUpRight size={17} />
            </button>
          </div>
          <section className="destinations">
            <div className="section-heading">
              <div>
                <h2>A change of scenery?</h2>
                <p>Start with a destination. Make it your own.</p>
              </div>
              <span className="section-kicker">
                <MapPin size={14} /> FROM DHAKA
              </span>
            </div>
            <div className="destination-grid">
              {(
                [
                  {
                    city: "Cox's Bazar",
                    title: "A little closer to the ocean",
                    type: "sea",
                    tag: "THE COAST IS CALLING",
                  },
                  {
                    city: "Sylhet",
                    title: "Take the scenic way",
                    type: "hills",
                    tag: "SLOW DOWN, LOOK AROUND",
                  },
                  {
                    city: "Chattogram",
                    title: "A new city. A fresh perspective.",
                    type: "city",
                    tag: "GO SOMEWHERE NEW",
                  },
                ] as const
              ).map((d) => (
                <button
                  className="destination-card"
                  key={d.city}
                  onClick={() =>
                    run({ ...query, from_city: "Dhaka", to_city: d.city })
                  }
                >
                  <div className="destination-image">
                    <DestinationArt type={d.type} />
                    <span>{d.tag}</span>
                  </div>
                  <div className="destination-info">
                    <div>
                      <h3>{d.city}</h3>
                      <p>{d.title}</p>
                    </div>
                    <span className="round-arrow">
                      <ArrowUpRight size={18} />
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </section>
          <div className="bottom-panels">
            <section className="whatsapp-promo">
              <div className="feature-icon mint">
                <MessageCircle size={27} />
              </div>
              <div>
                <span className="eyebrow">LESS CHECKING. MORE LIVING.</span>
                <h2>Good timing, delivered.</h2>
                <p>
                  Low seats, booking updates, and payment reminders.
                  <br />
                  Your journey can come straight to WhatsApp.
                </p>
                <button className="text-button" onClick={() => app.plan()}>
                  Create your first watch <ArrowRight size={15} />
                </button>
              </div>
              <Badge
                tone={app.config?.whatsapp_configured ? "green" : "neutral"}
              >
                {app.config?.whatsapp_configured
                  ? "Connected"
                  : "Setup required"}
              </Badge>
            </section>
            <section className="payment-promo panel">
              <ShieldCheck size={28} />
              <h3>
                Your journey.
                <br />
                Your final say.
              </h3>
              <p>
                We watch availability and help prepare your booking. You always
                complete the payment.
              </p>
              <span>
                YOU’RE IN CONTROL <ArrowUpRight size={14} />
              </span>
            </section>
          </div>
        </>
      )}
      {seatOffer && result && (
        <Seats
          offer={seatOffer}
          result={result}
          onClose={() => setSeatOffer(null)}
        />
      )}
    </div>
  );
}
function BusCard({
  offer: o,
  query,
  onSeats,
  onWatch,
}: {
  offer: Offer;
  query: SearchInput;
  onSeats: () => void;
  onWatch: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="bus-card panel">
      <div className="bus-card-main">
        <div className="operator">
          <span className="operator-avatar">{o.operator.slice(0, 1)}</span>
          <div>
            <h3>{o.operator}</h3>
            <p>{o.service_class}</p>
            <span className="bus-type">{busType(o.service_class)}</span>
          </div>
        </div>
        <div className="bus-times">
          <div>
            <strong>{o.departure}</strong>
            <small>{query.from_city}</small>
          </div>
          <div className="duration">
            <small>{o.duration || "Departure"}</small>
            <span>
              <i />
              <ArrowRight size={15} />
            </span>
          </div>
          <div>
            <strong>{o.arrival || "—"}</strong>
            <small>{query.to_city}</small>
          </div>
        </div>
        <div className="bus-fare">
          <small>from / seat</small>
          <strong>৳ {money(o.unit_fare)}</strong>
          <small>Before provider fees</small>
        </div>
      </div>
      <div className="bus-card-bottom">
        <span className={`seat-count ${o.seats_available <= 5 ? "low" : ""}`}>
          <span />
          {o.seats_available} seats available
        </span>
        <div>
          <button
            className="text-button"
            aria-expanded={expanded}
            onClick={() => setExpanded(!expanded)}
          >
            Route & stops <ChevronDown size={13} />
          </button>
          <button className="button secondary small" onClick={onWatch}>
            <Bell size={14} /> Watch bus
          </button>
          <button
            className="button primary small"
            onClick={onSeats}
            disabled={o.seats_available < query.seat_count || !!o.provider_note}
          >
            Select seats <ArrowRight size={14} />
          </button>
        </div>
      </div>
      {o.provider_note && <p className="provider-note">{o.provider_note}</p>}
      {expanded && (
        <div className="route-details">
          <div>
            <strong>Route</strong>
            <p>{o.route}</p>
          </div>
          <div>
            <strong>Boarding points</strong>
            <p>
              {o.boarding_points.join(" · ") ||
                "Check current stops with Shohoz."}
            </p>
          </div>
          <div>
            <strong>Dropping points</strong>
            <p>{o.dropping_points.join(" · ") || query.to_city}</p>
          </div>
        </div>
      )}
    </article>
  );
}
function Seats({
  offer,
  result,
  onClose,
}: {
  offer: Offer;
  result: SearchResult;
  onClose: () => void;
}) {
  const app = useApp();
  const [chosen, setChosen] = useState<string[]>([]);
  const map = useQuery({
    queryKey: ["seatmap", result.search_id, offer.id],
    queryFn: ({ signal }) =>
      api<SeatMap>(
        `/api/search/${result.search_id}/offers/${offer.id}/seats`,
        undefined,
        signal,
      ),
    retry: false,
    staleTime: 15000,
    refetchOnWindowFocus: false,
  });
  const groups = (values: number[]) =>
    values
      .sort((a, b) => a - b)
      .reduce<number[]>((all, value) => {
        if (!all.length || value - all[all.length - 1] > 12) all.push(value);
        return all;
      }, []);
  const xs = groups(map.data?.seats.map((s) => s.x) || []),
    ys = groups(map.data?.seats.map((s) => s.y) || []);
  const providerDate = dateLabel(
    result.query.journey_date + "T12:00:00+06:00",
    { year: "numeric" },
  ).replaceAll(" ", "-");
  const url =
    "https://www.shohoz.com/bus-tickets/booking/bus/search?" +
    new URLSearchParams({
      fromcity: result.query.from_city,
      tocity: result.query.to_city,
      doj: providerDate,
      dor: "",
    });
  function proceed(seats: string[]) {
    onClose();
    app.plan({
      offer,
      query: result.query,
      seats,
      intent: seats.length && result.booking_enabled ? "prepare" : "watch",
    });
  }
  return (
    <Modal
      title={offer.operator}
      eyebrow="FIND YOUR PLACE"
      onClose={onClose}
      wide
    >
      <p className="muted">
        {offer.departure} · {offer.service_class} · ৳ {money(offer.unit_fare)}{" "}
        per seat
      </p>
      {map.isPending ? (
        <div className="seat-loading">
          <Spinner label="Opening the live seat map…" />
        </div>
      ) : map.isError ? (
        <div className="seat-unavailable">
          <span className="empty-symbol">
            <ShieldCheck size={26} />
          </span>
          <h3>A quick stop at Shohoz</h3>
          <ErrorBox error={map.error} />
          <p>
            You can still save this departure and watch its available seat count
            here.
          </p>
          <div className="button-row">
            <a
              className="button secondary"
              href={url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open on Shohoz <ArrowUpRight size={16} />
            </a>
            <button className="button primary" onClick={() => proceed([])}>
              <Bell size={16} /> Watch this bus
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="seat-legend">
            <span>
              <i />
              Available
            </span>
            <span>
              <i className="selected" />
              Selected
            </span>
            <span>
              <i className="booked" />
              Unavailable
            </span>
            <span>
              <i className="restricted" />
              Restricted
            </span>
          </div>
          <div className="seat-layout">
            <div className="bus-shell">
              <div className="bus-front">
                FRONT OF BUS <Compass size={22} />
              </div>
              <div
                className="native-seat-map"
                style={{
                  gridTemplateColumns: `repeat(${Math.max(4, xs.length)},minmax(30px,1fr))`,
                }}
              >
                {map.data?.seats.map((s) => (
                  <button
                    className={`native-seat ${chosen.includes(s.label) ? "chosen" : s.female_only ? "restricted" : s.available ? "available" : "booked"}`}
                    aria-label={`Seat ${s.label}`}
                    aria-pressed={chosen.includes(s.label)}
                    disabled={!s.available || s.female_only}
                    key={s.label}
                    style={{
                      gridColumn:
                        xs.findIndex((x) => Math.abs(x - s.x) <= 12) + 1,
                      gridRow: ys.findIndex((y) => Math.abs(y - s.y) <= 12) + 1,
                    }}
                    onClick={() =>
                      setChosen((all) =>
                        all.includes(s.label)
                          ? all.filter((x) => x !== s.label)
                          : all.length < result.query.seat_count
                            ? [...all, s.label]
                            : all,
                      )
                    }
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="seat-summary">
              <h3>Your selection</h3>
              <p>{chosen.join(", ") || "Choose your preferred seats."}</p>
              <div className="seat-total">
                <span>Estimated seat fare</span>
                <strong>
                  ৳ {money(chosen.length * Number(offer.unit_fare))}
                </strong>
                <small>Provider fees are checked before payment.</small>
              </div>
              <p>
                Choose {result.query.seat_count} seat(s). Selecting here saves
                your preference; it does not hold seats.
              </p>
              <button
                className="button primary full"
                disabled={chosen.length !== result.query.seat_count}
                onClick={() => proceed(chosen)}
              >
                {app.config?.mode === "live"
                  ? "Continue to booking"
                  : "Watch this bus"}
                <ArrowRight size={16} />
              </button>
              <button className="text-button" onClick={() => proceed([])}>
                Watch without seat preferences
              </button>
            </div>
          </div>
        </>
      )}
    </Modal>
  );
}
