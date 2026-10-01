import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  BusFront,
  Check,
  Eye,
  EyeOff,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { useApp } from "../lib/context";
import {
  api,
  clockTime,
  dateOffset,
  localDateTime,
  money,
  today,
} from "../lib/api";
import type { BookingInput, Job, Passenger, User } from "../lib/types";
import { Badge, ErrorBox, Modal, Spinner } from "./ui";

export function AuthDialog() {
  const app = useApp();
  const [register, setRegister] = useState(true);
  const [visible, setVisible] = useState(false);
  const [recover, setRecover] = useState(false);
  const auth = useMutation({
    mutationFn: (body: Record<string, FormDataEntryValue>) =>
      api<{ user: User }>(`/api/auth/${register ? "register" : "login"}`, body),
    onSuccess: (data) => app.signedIn(data.user),
  });
  if (recover)
    return (
      <RecoverAccount
        onBack={() => {
          setRecover(false);
          setRegister(false);
        }}
        onClose={() => app.setAuthOpen(false)}
      />
    );
  return (
    <Modal
      title={register ? "Your next chapter starts here." : "Welcome back."}
      eyebrow="YOUR PERSONAL TRAVEL DESK"
      onClose={() => app.setAuthOpen(false)}
    >
      <div className="auth-intro">
        <span className="feature-icon purple">
          <BusFront size={23} />
        </span>
        <p>
          {register
            ? "Save journeys, watch availability, and keep your plans in one place."
            : "Pick up where you left off. Your journeys are waiting."}
        </p>
      </div>
      <form
        className="stack-form"
        onSubmit={(e) => {
          e.preventDefault();
          auth.mutate(Object.fromEntries(new FormData(e.currentTarget)));
        }}
      >
        {register && (
          <label>
            Full name
            <input
              name="name"
              placeholder="Your name"
              autoComplete="name"
              required
              maxLength={80}
            />
          </label>
        )}
        <label>
          Email address
          <input
            name="email"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            required
            maxLength={120}
          />
        </label>
        <label>
          Password
          <div className="password-field">
            <input
              name="password"
              type={visible ? "text" : "password"}
              placeholder="At least 12 characters"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={12}
              maxLength={200}
            />
            <button
              type="button"
              className="icon-button"
              aria-label={visible ? "Hide password" : "Show password"}
              onClick={() => setVisible(!visible)}
            >
              {visible ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
        </label>
        <ErrorBox error={auth.error} />
        <button className="button primary full" disabled={auth.isPending}>
          {auth.isPending ? (
            <Spinner label="One moment…" />
          ) : (
            <>
              {register ? "Create account" : "Sign in"}
              <ArrowRight size={16} />
            </>
          )}
        </button>
      </form>
      <button
        className="auth-toggle text-button"
        onClick={() => {
          setRegister(!register);
          auth.reset();
        }}
      >
        {register
          ? "Already have an account? Sign in"
          : "New here? Create an account"}
      </button>
      <p className="secure-note">
        <LockKeyhole size={13} /> Your bookings are private to your account.
      </p>
      {!register && (
        <button
          className="text-button auth-toggle"
          onClick={() => setRecover(true)}
        >
          Use a recovery code
        </button>
      )}
    </Modal>
  );
}
function RecoverAccount({
  onBack,
  onClose,
}: {
  onBack: () => void;
  onClose: () => void;
}) {
  const reset = useMutation({
    mutationFn: (body: Record<string, FormDataEntryValue>) =>
      api<{ message: string }>("/api/auth/recover", body),
  });
  return (
    <Modal
      title="Get back to your journeys."
      eyebrow="ACCOUNT RECOVERY"
      onClose={onClose}
    >
      <p className="muted">
        Use the recovery code you saved from Connections. This signs out all
        existing sessions.
      </p>
      {reset.isSuccess ? (
        <p role="status">{reset.data.message}</p>
      ) : (
        <form
          className="stack-form"
          onSubmit={(e) => {
            e.preventDefault();
            reset.mutate(Object.fromEntries(new FormData(e.currentTarget)));
          }}
        >
          <label>
            Email address
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={120}
            />
          </label>
          <label>
            Saved recovery code
            <input
              name="code"
              autoComplete="off"
              required
              minLength={20}
              maxLength={100}
            />
          </label>
          <label>
            New password
            <input
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={200}
            />
          </label>
          <ErrorBox error={reset.error} />
          <button className="button primary" disabled={reset.isPending}>
            Reset password
          </button>
        </form>
      )}
      <button className="text-button auth-toggle" onClick={onBack}>
        Back to sign in
      </button>
    </Modal>
  );
}
export function BookingDialog() {
  const app = useApp();
  const navigate = useNavigate();
  const selected =
    app.booking && app.booking !== "general" ? app.booking : null;
  const demo = app.config?.mode === "demo" && !selected;
  const [watch, setWatch] = useState(
    selected ? selected.intent !== "prepare" : false,
  );
  const departureCutoff = selected
    ? localDateTime(
        new Date(
          new Date(
            `${selected.query.journey_date}T${clockTime(selected.offer.departure)}:00+06:00`,
          ).getTime() -
            (app.config?.departure_buffer_minutes ?? 5) * 60000,
        ),
      )
    : undefined;
  const [requestKey] = useState(() => crypto.randomUUID());
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<BookingInput>(() => ({
    from_city: selected?.query.from_city || "Dhaka",
    to_city: selected?.query.to_city || "Bogura",
    journey_date: selected?.query.journey_date || dateOffset(1),
    seat_count: selected?.query.seat_count || 1,
    departure_start: selected ? clockTime(selected.offer.departure) : "00:00",
    departure_end: selected ? clockTime(selected.offer.departure) : "23:59",
    buy_after: localDateTime(new Date(Date.now() - 60000)),
    buy_before:
      departureCutoff &&
      departureCutoff < localDateTime(new Date(Date.now() + 3600000))
        ? departureCutoff
        : localDateTime(new Date(Date.now() + 3600000)),
    max_total: selected
      ? String(
          Math.ceil(
            Number(selected.offer.unit_fare) * selected.query.seat_count * 1.1,
          ),
        )
      : "1500",
    seat_preference: "any",
    operators: selected ? [selected.offer.operator] : [],
    boarding_point: "",
    contact_phone: demo ? "+8801700000000" : "",
    contact_email: app.user!.email,
    whatsapp_phone: demo ? "+8801700000000" : "",
    whatsapp_opt_in: false,
    low_seat_threshold: 5,
    seat_fallback: "wait",
    passengers: Array.from(
      { length: selected?.query.seat_count || 1 },
      (_, i) => ({
        first_name: demo
          ? "Sample"
          : i === 0
            ? app.user!.name.split(" ")[0]
            : "",
        last_name: demo
          ? `Rider ${i + 1}`
          : i === 0
            ? app.user!.name.split(" ").slice(1).join(" ")
            : "",
        gender: "",
      }),
    ),
  }));
  const save = useMutation({
    mutationFn: (body: BookingInput) => api<{ job: Job }>("/api/jobs", body),
    onSuccess: () => {
      app.setBooking(null);
      app.refresh();
      navigate("/journeys");
      app.notify(
        watch
          ? "Your live availability watch is saved."
          : "Your journey is saved. We’ll keep an eye on it.",
      );
    },
  });
  const update = <K extends keyof BookingInput>(
    key: K,
    value: BookingInput[K],
  ) => setForm((old) => ({ ...old, [key]: value }));
  function chooseIntent(nextWatch: boolean) {
    setWatch(nextWatch);
    if (nextWatch && demo)
      setForm((old) => ({
        ...old,
        contact_phone:
          old.contact_phone === "+8801700000000" ? "" : old.contact_phone,
        whatsapp_phone:
          old.whatsapp_phone === "+8801700000000" ? "" : old.whatsapp_phone,
        passengers: old.passengers.map((p, i) =>
          p.first_name === "Sample"
            ? {
                ...p,
                first_name: i === 0 ? app.user!.name.split(" ")[0] : "",
                last_name:
                  i === 0 ? app.user!.name.split(" ").slice(1).join(" ") : "",
              }
            : p,
        ),
      }));
  }
  const passenger = (index: number, key: keyof Passenger, value: string) =>
    setForm((old) => ({
      ...old,
      passengers: old.passengers.map((p, i) =>
        i === index ? { ...p, [key]: value } : p,
      ),
    }));
  function seatCount(count: number) {
    setForm((old) => ({
      ...old,
      seat_count: count,
      passengers: Array.from(
        { length: count },
        (_, i) =>
          old.passengers[i] || {
            first_name: demo && !watch ? "Sample" : "",
            last_name: demo && !watch ? `Rider ${i + 1}` : "",
            gender: "",
          },
      ),
    }));
  }
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    save.mutate({
      ...form,
      monitor_only: watch,
      request_key: requestKey,
      operators: form.operators.map((value) => value.trim()).filter(Boolean),
      buy_after: form.buy_after + ":00+06:00",
      buy_before: form.buy_before + ":00+06:00",
      ...(selected
        ? {
            selected_offer_id: selected.offer.id,
            preferred_seats: selected.seats,
            monitor_only: watch,
          }
        : {}),
    });
  }
  return (
    <Modal
      title={watch ? "Make room for your plans." : "A journey, on your terms."}
      eyebrow={watch ? "CREATE A LIVE WATCH" : "PLAN YOUR JOURNEY"}
      onClose={() => {
        if (!save.isPending) app.setBooking(null);
      }}
      wide
    >
      <div className="wizard-steps">
        {["Your journey", "Time & budget", "Travelers & alerts"].map(
          (label, i) => (
            <div
              className={i === step ? "current" : i < step ? "complete" : ""}
              key={label}
            >
              <span>{i < step ? <Check size={15} /> : i + 1}</span>
              <strong>{label}</strong>
              {i < 2 && <i />}
            </div>
          ),
        )}
      </div>
      {selected && (
        <div className="selection-banner">
          <span className="feature-icon purple">
            <BusFront size={21} />
          </span>
          <div>
            <strong>
              {selected.offer.operator} · {selected.offer.departure}
            </strong>
            <p>
              {selected.query.from_city} → {selected.query.to_city}
              {selected.seats.length > 0
                ? ` · Seats ${selected.seats.join(", ")}`
                : ""}
            </p>
          </div>
          <Badge tone={watch ? "green" : "purple"}>
            {watch ? "Watch only" : "Selected bus"}
          </Badge>
        </div>
      )}
      <form className="booking-form" onSubmit={submit}>
        {step === 0 && (
          <fieldset className="intent-options">
            <legend>WHAT WOULD YOU LIKE US TO DO?</legend>
            <label className={`intent-choice ${watch ? "chosen" : ""}`}>
              <input
                type="radio"
                name="booking_intent"
                checked={watch}
                onChange={() => chooseIntent(true)}
              />
              <span>
                <strong>Notify me only</strong>
                <small>
                  Monitor availability and alert me. Never select or reserve
                  seats.
                </small>
              </span>
            </label>
            <label className={`intent-choice ${!watch ? "chosen" : ""}`}>
              <input
                type="radio"
                name="booking_intent"
                checked={!watch}
                disabled={!!selected && app.config?.mode !== "live"}
                onChange={() => chooseIntent(false)}
              />
              <span>
                <strong>
                  {demo
                    ? "Try booking preparation · demo"
                    : "Prepare a booking in my time window"}
                </strong>
                <small>
                  {selected && app.config?.mode !== "live"
                    ? "Live reservations need provider setup. Watching is available now."
                    : "Prepare eligible seats within my limits. I will complete payment myself."}
                </small>
              </span>
            </label>
          </fieldset>
        )}
        {step === 0 && (
          <>
            <h3>The first step to getting there.</h3>
            <p className="muted">
              Choose your route and departure preferences.
            </p>
            <div className="form-grid">
              <label>
                From
                <input
                  name="from_city"
                  list="booking-cities"
                  required
                  minLength={2}
                  maxLength={60}
                  readOnly={!!selected}
                  value={form.from_city}
                  onChange={(e) => update("from_city", e.target.value)}
                />
              </label>
              <label>
                To
                <input
                  name="to_city"
                  list="booking-cities"
                  required
                  minLength={2}
                  maxLength={60}
                  readOnly={!!selected}
                  value={form.to_city}
                  onChange={(e) => update("to_city", e.target.value)}
                />
              </label>
              <label>
                Journey date
                <input
                  name="journey_date"
                  type="date"
                  required
                  min={today()}
                  readOnly={!!selected}
                  value={form.journey_date}
                  onChange={(e) => update("journey_date", e.target.value)}
                />
              </label>
              <label>
                Passengers
                <select
                  name="seat_count"
                  aria-label="Passengers"
                  disabled={!!selected}
                  value={form.seat_count}
                  onChange={(e) => seatCount(Number(e.target.value))}
                >
                  {[1, 2, 3, 4].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label>
                Departure from
                <input
                  type="time"
                  name="departure_start"
                  required
                  readOnly={!!selected}
                  value={form.departure_start}
                  onChange={(e) => update("departure_start", e.target.value)}
                />
              </label>
              <label>
                Departure until
                <input
                  type="time"
                  name="departure_end"
                  required
                  readOnly={!!selected}
                  value={form.departure_end}
                  onChange={(e) => update("departure_end", e.target.value)}
                />
              </label>
              <label>
                Preferred operator
                <input
                  name="operators"
                  placeholder="Any operator"
                  readOnly={!!selected}
                  value={form.operators.join(", ")}
                  onChange={(e) =>
                    update(
                      "operators",
                      e.target.value.split(",").map((x) => x.trim()),
                    )
                  }
                />
              </label>
              <label>
                Seat preference
                <select
                  name="seat_preference"
                  value={form.seat_preference}
                  onChange={(e) => update("seat_preference", e.target.value)}
                >
                  <option value="any">Any available seat</option>
                  <option value="front">Near the front</option>
                  <option value="middle">Near the middle</option>
                  <option value="window">Window · manual review</option>
                  <option value="aisle">Aisle · manual review</option>
                </select>
              </label>
              {!!selected?.seats.length && (
                <label>
                  If my selected seats disappear
                  <select
                    name="seat_fallback"
                    value={form.seat_fallback}
                    onChange={(e) =>
                      update("seat_fallback", e.target.value as "wait" | "any")
                    }
                  >
                    <option value="wait">Wait for these exact seats</option>
                    <option value="any">
                      Allow other eligible seats on this bus
                    </option>
                  </select>
                </label>
              )}
            </div>
            <datalist id="booking-cities">
              {[
                "Dhaka",
                "Bogura",
                "Chattogram",
                "Cox's Bazar",
                "Sylhet",
                "Rajshahi",
                "Khulna",
                "Rangpur",
              ].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </datalist>
          </>
        )}
        {step === 1 && (
          <>
            <h3>Good timing is everything.</h3>
            <p className="muted">
              Set your {watch ? "watching" : "buying"} window. All times are in
              Bangladesh (Asia/Dhaka).
            </p>
            <div className="form-grid">
              <label>
                Start watching
                <input
                  name="buy_after"
                  type="datetime-local"
                  required
                  value={form.buy_after}
                  onChange={(e) => update("buy_after", e.target.value)}
                />
              </label>
              <label>
                {watch ? "Watch until" : "Buy before"}
                <input
                  name="buy_before"
                  max={departureCutoff}
                  type="datetime-local"
                  required
                  min={form.buy_after}
                  value={form.buy_before}
                  onChange={(e) => update("buy_before", e.target.value)}
                />
              </label>
              <label>
                Total budget · BDT
                <input
                  name="max_total"
                  type="number"
                  min="1"
                  max="100000"
                  step="0.01"
                  required
                  value={form.max_total}
                  onChange={(e) => update("max_total", e.target.value)}
                />
              </label>
              <label>
                Boarding point
                <input
                  name="boarding_point"
                  list="boarding-points"
                  placeholder="Any available point"
                  maxLength={120}
                  value={form.boarding_point}
                  onChange={(e) => update("boarding_point", e.target.value)}
                />
                <datalist id="boarding-points">
                  {selected?.offer.boarding_points.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </datalist>
              </label>
            </div>
            <div className="form-callout">
              <ShieldCheck size={21} />
              <p>
                {watch
                  ? "We’ll monitor this exact departure. No seats will be reserved or purchased."
                  : demo
                    ? "This is a demo journey with simulated seats and payment. No real ticket will be purchased."
                    : "We’ll recheck fares and availability before preparing your booking. Payment is always completed by you."}
              </p>
              <p className="muted small-text">
                If seats run low before your window, we can notify you but will
                not reserve early. If a payment deadline is missed, we stop and
                ask you to check the provider; we never automatically book
                again.
              </p>
            </div>
          </>
        )}
        {step === 2 && (
          <>
            <div className="wizard-review">
              <div>
                <strong>
                  {form.from_city} <ArrowRight size={14} /> {form.to_city}
                </strong>
                <small>
                  {form.journey_date} · {form.seat_count} passenger(s)
                </small>
              </div>
              <div>
                <small>Total budget</small>
                <strong>৳ {money(form.max_total)}</strong>
              </div>
            </div>
            {form.passengers.map((p, i) => (
              <fieldset className="passenger-fields" key={i}>
                <legend>TRAVELER {i + 1}</legend>
                <div className="form-grid three">
                  <label>
                    First name
                    <input
                      name={`first_name_${i}`}
                      required
                      maxLength={60}
                      value={p.first_name}
                      onChange={(e) =>
                        passenger(i, "first_name", e.target.value)
                      }
                    />
                  </label>
                  <label>
                    Last name
                    <input
                      name={`last_name_${i}`}
                      required
                      maxLength={60}
                      value={p.last_name}
                      onChange={(e) =>
                        passenger(i, "last_name", e.target.value)
                      }
                    />
                  </label>
                  <label>
                    Gender
                    <select
                      name={`gender_${i}`}
                      aria-label={`Traveler ${i + 1} gender`}
                      required
                      value={p.gender}
                      onChange={(e) => passenger(i, "gender", e.target.value)}
                    >
                      <option value="">Choose</option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                    </select>
                  </label>
                </div>
              </fieldset>
            ))}
            <div className="form-grid">
              <label>
                Contact phone
                <input
                  name="contact_phone"
                  type="tel"
                  required
                  placeholder="+8801712345678"
                  value={form.contact_phone}
                  onChange={(e) => update("contact_phone", e.target.value)}
                />
              </label>
              <label>
                Contact email
                <input
                  name="contact_email"
                  type="email"
                  required
                  maxLength={120}
                  value={form.contact_email}
                  onChange={(e) => update("contact_email", e.target.value)}
                />
              </label>
            </div>
            <div className="whatsapp-option">
              <label className="check-label">
                <input
                  name="whatsapp_opt_in"
                  type="checkbox"
                  checked={form.whatsapp_opt_in}
                  onChange={(e) => update("whatsapp_opt_in", e.target.checked)}
                />
                <strong>Send me booking updates on WhatsApp</strong>
              </label>
              <p>
                {demo && !watch
                  ? "Messages are previews in demo mode and will not be sent."
                  : app.config?.whatsapp_configured
                    ? "By opting in, you agree to receive updates about this journey."
                    : "WhatsApp setup is pending. Updates will appear in your workspace until messaging is connected."}
              </p>
              {form.whatsapp_opt_in && (
                <div className="form-grid">
                  <label>
                    WhatsApp number
                    <input
                      name="whatsapp_phone"
                      type="tel"
                      required
                      placeholder="+8801712345678"
                      value={form.whatsapp_phone}
                      onChange={(e) => update("whatsapp_phone", e.target.value)}
                    />
                  </label>
                  <label>
                    Alert when seats fall to
                    <input
                      name="low_seat_threshold"
                      type="number"
                      required
                      min="1"
                      max="40"
                      value={form.low_seat_threshold}
                      onChange={(e) =>
                        update("low_seat_threshold", Number(e.target.value))
                      }
                    />
                  </label>
                </div>
              )}
            </div>
          </>
        )}
        <ErrorBox error={save.error} />
        <div className="wizard-footer">
          <span>Step {step + 1} of 3</span>
          <div>
            {step > 0 && (
              <button
                type="button"
                className="button secondary"
                disabled={save.isPending}
                onClick={() => setStep(step - 1)}
              >
                <ArrowLeft size={15} /> Back
              </button>
            )}
            <button
              type="submit"
              className="button primary"
              disabled={save.isPending}
            >
              {save.isPending ? (
                <Spinner label="Saving…" />
              ) : step < 2 ? (
                <>
                  Continue <ArrowRight size={16} />
                </>
              ) : (
                <>
                  <Bell size={16} />
                  {watch ? "Save live watch" : "Start watching"}
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
