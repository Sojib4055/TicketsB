import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Bell,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Download,
  ExternalLink,
  Pause,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
  Ticket,
  X,
} from "lucide-react";
import { api, dateLabel, money, statusLabel, when } from "../lib/api";
import { useApp } from "../lib/context";
import type { Detail, Job } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, Spinner } from "../components/ui";
const finished = ["CONFIRMED", "CANCELLED", "EXPIRED"];
function JobBadge({ job }: { job: Job }) {
  const tone = ["CONFIRMED", "MONITORING"].includes(job.status)
    ? "green"
    : ["AWAITING_PAYMENT", "PREPARING", "NEEDS_ATTENTION"].includes(job.status)
      ? "amber"
      : job.status === "SCHEDULED"
        ? "purple"
        : "neutral";
  return (
    <Badge tone={tone}>
      {job.mode === "demo" && job.status === "CONFIRMED"
        ? "Demo completed"
        : statusLabel[job.status] || job.status}
    </Badge>
  );
}
export default function Journeys() {
  const app = useApp();
  const [filter, setFilter] = useState("all");
  const [params, setParams] = useSearchParams();
  const selected =
    params.get("job") || new URLSearchParams(window.location.search).get("job");
  const jobs = app.jobs.filter(
    (j) =>
      filter === "all" ||
      (filter === "active"
        ? !finished.includes(j.status)
        : finished.includes(j.status)),
  );
  const metrics = [
    {
      icon: Bell,
      label: "Watching for you",
      value: app.jobs.filter((j) =>
        ["SCHEDULED", "MONITORING", "PREPARING"].includes(j.status),
      ).length,
      tone: "purple",
      caption: "Your active journey watches",
    },
    {
      icon: Clock3,
      label: "Ready for your next step",
      value: app.jobs.filter((j) => j.status === "AWAITING_PAYMENT").length,
      tone: "peach",
      caption: "Bookings awaiting your payment",
    },
    {
      icon: CheckCircle2,
      label: "Journeys confirmed",
      value: app.jobs.filter((j) => j.status === "CONFIRMED").length,
      tone: "mint",
      caption:
        app.config?.mode === "demo"
          ? "Includes simulated demo journeys"
          : "Confirmed by the provider",
    },
  ];
  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ALL YOUR PLANS, ONE CALM SPACE</p>
          <h1>Your journeys, taken care of.</h1>
          <p>From a first thought to your next departure. Keep it all here.</p>
        </div>
        <button className="button primary" onClick={() => app.plan()}>
          <Plus size={17} /> Plan a journey
        </button>
      </div>
      <div className="journey-metrics">
        {metrics.map(({ icon: Icon, label, value, tone, caption }) => (
          <div className="metric panel" key={label}>
            <div>
              <span className={`feature-icon ${tone}`}>
                <Icon size={20} />
              </span>
              <span>{label}</span>
            </div>
            <strong>{value.toString().padStart(2, "0")}</strong>
            <small>{caption}</small>
          </div>
        ))}
      </div>
      <div className="section-toolbar">
        <div className="tabs">
          {[
            ["all", "All journeys"],
            ["active", "Active"],
            ["past", "Past journeys"],
          ].map(([value, label]) => (
            <button
              key={value}
              className={filter === value ? "active" : ""}
              onClick={() => setFilter(value)}
            >
              {label}
              {value === "all" && <span>{app.jobs.length}</span>}
            </button>
          ))}
        </div>
        <span className="live-updates">
          <span className={`status-dot ${app.connected ? "" : "offline"}`} />
          {app.connected ? "Updates automatically" : "Reconnecting"}
        </span>
      </div>
      <ErrorBox error={app.jobsError} retry={app.refresh} />
      {!jobs.length ? (
        <div className="panel">
          <Empty
            icon={<Ticket size={30} />}
            title={
              app.user
                ? "A good journey starts with a plan."
                : "Make a little room for your next adventure."
            }
            action={
              <button className="button primary" onClick={() => app.plan()}>
                <Plus size={16} />{" "}
                {app.user
                  ? "Plan your first journey"
                  : "Create your travel desk"}
              </button>
            }
          >
            Save your route, set a time window, and leave the availability
            checks to us.
          </Empty>
        </div>
      ) : (
        <div className="journeys-list">
          {jobs.map((job) => (
            <article className="journey-card panel" key={job.id}>
              <div className="journey-card-heading">
                <div>
                  <span className="journey-type">
                    {job.request.monitor_only
                      ? "LIVE AVAILABILITY WATCH"
                      : job.mode === "demo"
                        ? "DEMO JOURNEY"
                        : "SHOHOZ BOOKING"}
                  </span>
                  <h2>
                    {job.request.from_city} <ArrowRight size={21} />{" "}
                    {job.request.to_city}
                  </h2>
                  <p>
                    <CalendarDays size={13} />
                    {dateLabel(job.request.journey_date + "T12:00:00+06:00", {
                      weekday: "short",
                      year: "numeric",
                    })}
                    <span>·</span>
                    {job.request.seat_count} passenger(s)
                  </p>
                </div>
                <JobBadge job={job} />
              </div>
              <div className="journey-card-grid">
                <div>
                  <small>Departure preference</small>
                  <strong>
                    {job.request.departure_start.slice(0, 5)} –{" "}
                    {job.request.departure_end.slice(0, 5)}
                  </strong>
                </div>
                <div>
                  <small>Watching window · Dhaka</small>
                  <strong>
                    {when(job.request.buy_after)} →{" "}
                    {when(job.request.buy_before)}
                  </strong>
                </div>
                <div>
                  <small>Total budget</small>
                  <strong>
                    ৳ {money(job.request.max_total)} <em>BDT</em>
                  </strong>
                </div>
              </div>
              <div className="journey-card-bottom">
                <p>
                  <span className="status-dot" />
                  {job.data.message || "Your request is queued for monitoring."}
                </p>
                <button
                  className={`button small ${job.status === "AWAITING_PAYMENT" ? "primary" : "secondary"}`}
                  onClick={() =>
                    setParams({
                      job: job.id,
                      ...(job.status === "AWAITING_PAYMENT" &&
                      job.mode === "live"
                        ? { pay: "1" }
                        : {}),
                    })
                  }
                >
                  {job.status === "AWAITING_PAYMENT"
                    ? "Review & pay"
                    : "View journey"}
                  <ArrowUpRight size={15} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {selected && app.user && (
        <JourneyDetail
          id={selected}
          onClose={() => {
            setParams({});
            if (window.location.search) {
              window.history.replaceState(
                null,
                "",
                window.location.pathname + window.location.hash,
              );
            }
          }}
        />
      )}
    </div>
  );
}
function JourneyDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const app = useApp();
  const [provider, setProvider] = useState(false);
  const [params] = useSearchParams();
  const openedPayment = useRef(false);
  const detail = useQuery({
    queryKey: ["detail", app.user?.id, id],
    queryFn: ({ signal }) => api<Detail>(`/api/jobs/${id}`, undefined, signal),
    enabled: !!app.user,
    refetchInterval: 5000,
  });
  const action = useMutation({
    mutationFn: (kind: string) =>
      api(`/api/jobs/${id}/action`, { action: kind }),
    onSuccess: (_, kind) => {
      app.refresh();
      void detail.refetch();
      if (kind === "reconnect") setProvider(true);
    },
  });
  const job = detail.data?.job;
  const request = job?.request;
  const data = job?.data;
  useEffect(() => {
    if (
      !openedPayment.current &&
      params.get("pay") === "1" &&
      detail.data?.session_available
    ) {
      openedPayment.current = true;
      setProvider(true);
    }
  }, [params, detail.data?.session_available]);
  return (
    <Modal
      title={
        request ? `${request.from_city} → ${request.to_city}` : "Your journey"
      }
      eyebrow="EVERY DETAIL, IN ONE PLACE"
      onClose={onClose}
      wide
    >
      {detail.isPending ? (
        <Spinner label="Opening your journey…" />
      ) : !job || !request || !data ? (
        <ErrorBox error={detail.error} />
      ) : (
        <>
          <div className="detail-status">
            <JobBadge job={job} />
            <span>
              {job.request.monitor_only
                ? "Availability watch · no reservations"
                : job.mode === "demo"
                  ? "Simulated journey · no real ticket"
                  : "Shohoz · private booking"}
            </span>
          </div>
          <p className="detail-message">
            {data.message || "Your request is waiting to be checked."}
          </p>
          <dl className="detail-grid">
            <div>
              <dt>Journey date</dt>
              <dd>
                {dateLabel(request.journey_date + "T12:00:00+06:00", {
                  year: "numeric",
                })}{" "}
                · {request.seat_count} seat(s)
              </dd>
            </div>
            <div>
              <dt>Time window · Bangladesh</dt>
              <dd>
                {when(request.buy_after)} → {when(request.buy_before)}
              </dd>
            </div>
            <div>
              <dt>Total budget</dt>
              <dd>৳ {money(request.max_total)}</dd>
            </div>
            <div>
              <dt>Travelers</dt>
              <dd>
                {request.passengers
                  .map((p) => `${p.first_name} ${p.last_name}`)
                  .join(", ")}
              </dd>
            </div>
            {data.seats && (
              <div>
                <dt>Selected seats</dt>
                <dd>{data.seats.join(", ")}</dd>
              </div>
            )}
            {!!request.preferred_seats?.length && (
              <div>
                <dt>Requested seats</dt>
                <dd>
                  {request.preferred_seats.join(", ")} ·{" "}
                  {data.preferred_seats_status || "Awaiting seat map"}
                  {data.missing_seats?.length
                    ? ` (unavailable: ${data.missing_seats.join(", ")})`
                    : ""}
                  <small>
                    {request.seat_fallback === "any"
                      ? "Other eligible seats allowed"
                      : "Wait for these exact seats"}
                  </small>
                </dd>
              </div>
            )}
            {data.reference && (
              <div>
                <dt>
                  {job.mode === "demo"
                    ? "Demo reference"
                    : "Provider reference"}
                </dt>
                <dd>{data.reference}</dd>
              </div>
            )}
          </dl>
          {job.status === "AWAITING_PAYMENT" && (
            <div className="payment-box">
              <span className="feature-icon peach">
                <ShieldCheck size={23} />
              </span>
              <div>
                <h3>
                  {job.mode === "demo"
                    ? "Try the manual payment step."
                    : "Your booking is ready for you."}
                </h3>
                <p>
                  Total <strong>৳ {money(data.total)} BDT</strong>
                  {data.expires_at && (
                    <>
                      {" "}
                      · <Countdown expiry={data.expires_at} />
                    </>
                  )}
                </p>
                <p>
                  {job.mode === "demo"
                    ? "This simulates you completing payment. It does not charge you or purchase a real ticket."
                    : "Complete payment in the provider session. We’ll wait for Shohoz to confirm your ticket."}
                </p>
                {job.mode === "demo" && (
                  <button
                    className="button primary"
                    disabled={action.isPending}
                    onClick={() => action.mutate("demo_pay")}
                  >
                    Simulate my payment <ArrowRight size={16} />
                  </button>
                )}
                {job.mode === "live" && detail.data?.session_available && (
                  <button
                    className="button primary"
                    onClick={() => setProvider(true)}
                  >
                    Pay in my provider session <ArrowRight size={16} />
                  </button>
                )}
              </div>
            </div>
          )}
          <ErrorBox error={action.error || detail.error} />
          <div className="button-row detail-actions">
            {["SCHEDULED", "MONITORING"].includes(job.status) && (
              <button
                className="button secondary"
                disabled={action.isPending}
                onClick={() => action.mutate("pause")}
              >
                <Pause size={15} /> Pause monitoring
              </button>
            )}
            {detail.data?.can_resume && (
              <button
                className="button secondary"
                disabled={action.isPending}
                onClick={() => action.mutate("resume")}
              >
                <Play size={15} /> Resume monitoring
              </button>
            )}
            {["SCHEDULED", "MONITORING", "PAUSED"].includes(job.status) && (
              <button
                className="button danger"
                disabled={action.isPending}
                onClick={() => action.mutate("cancel")}
              >
                <X size={15} /> Cancel request
              </button>
            )}
            {detail.data?.session_available && (
              <button
                className="button primary"
                onClick={() => setProvider(true)}
              >
                Open provider session <ExternalLink size={15} />
              </button>
            )}
            {!detail.data?.session_available &&
              detail.data?.session_recoverable &&
              ["NEEDS_ATTENTION", "AWAITING_PAYMENT", "CONFIRMED"].includes(
                job.status,
              ) && (
                <button
                  className="button primary"
                  disabled={action.isPending}
                  onClick={() => action.mutate("reconnect")}
                >
                  <RefreshCw size={15} /> Reconnect saved session
                </button>
              )}
            {data.ticket_available && (
              <a className="button primary" href={`/api/jobs/${id}/ticket`}>
                <Download size={15} /> Download ticket PDF
              </a>
            )}
            {["NEEDS_ATTENTION", "AWAITING_PAYMENT", "CONFIRMED"].includes(
              job.status,
            ) && (
              <button
                className="button secondary"
                disabled={action.isPending}
                onClick={() => action.mutate("close")}
              >
                Close request / session
              </button>
            )}
          </div>
          {data.recovery_required && (
            <p className="connection-note">
              This booking may already have reserved seats or received payment.
              Reconnect and review its status with Shohoz before creating
              another request. Automatic preparation is stopped.
            </p>
          )}
          {job.mode === "live" &&
            ["NEEDS_ATTENTION", "AWAITING_PAYMENT"].includes(job.status) && (
              <label className="payment-link">
                Open this private journey on another device
                <input
                  readOnly
                  value={`${window.location.origin}/#/journeys?job=${id}&pay=1`}
                  onFocus={(e) => e.target.select()}
                />
                <small>
                  Copy this link and sign in to the same account. The provider
                  session stays on this server.
                </small>
              </label>
            )}
          {["NEEDS_ATTENTION", "AWAITING_PAYMENT"].includes(job.status) && (
            <p className="muted small-text">
              Closing a request does not cancel a reservation with Shohoz. Check
              its status with the provider before creating another booking.
            </p>
          )}
          {!!data.offers?.length && (
            <section className="matching-offers">
              <h3>Matching departures</h3>
              {data.offers.map((o) => (
                <div key={o.id}>
                  <span>
                    <strong>{o.operator}</strong>
                    <small>
                      {o.departure} · {o.seats_available} seats listed
                    </small>
                  </span>
                  <strong>৳ {money(o.total || o.unit_fare)}</strong>
                </div>
              ))}
            </section>
          )}
          <h3 className="activity-heading">Journey activity</h3>
          <ol className="timeline">
            {detail.data?.events.map((e, i) => (
              <li key={i}>
                <span />
                <div>
                  {e.message}
                  <small>{when(e.created)}</small>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
      {provider && (
        <ProviderSession id={id} onClose={() => setProvider(false)} />
      )}
    </Modal>
  );
}
function Countdown({ expiry }: { expiry: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(
    0,
    Math.floor((new Date(expiry).getTime() - now) / 1000),
  );
  return (
    <span className="countdown">
      {seconds
        ? `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s remaining`
        : "Payment window ended"}
    </span>
  );
}
function ProviderSession({ id, onClose }: { id: string; onClose: () => void }) {
  const [image, setImage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(false);
  const busyRef = useRef(false);
  const alive = useRef(true);
  const imageRef = useRef("");
  async function load(signal?: AbortSignal) {
    try {
      const response = await fetch(`/api/jobs/${id}/session`, {
        credentials: "same-origin",
        cache: "no-store",
        signal,
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error);
      }
      const blob = await response.blob();
      if (!alive.current) return;
      const url = URL.createObjectURL(blob);
      if (imageRef.current) URL.revokeObjectURL(imageRef.current);
      imageRef.current = url;
      setImage(url);
    } catch (e) {
      if (
        alive.current &&
        !(e instanceof DOMException && e.name === "AbortError")
      )
        setError((e as Error).message);
    }
  }
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    let timer: number;
    async function poll() {
      if (!busyRef.current) await load(controller.signal);
      if (alive.current) timer = window.setTimeout(poll, 3000);
    }
    void poll();
    return () => {
      alive.current = false;
      controller.abort();
      clearTimeout(timer);
      if (imageRef.current) URL.revokeObjectURL(imageRef.current);
    };
  }, [id]);
  async function act(body: unknown) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      await api(`/api/jobs/${id}/session`, body);
      if (alive.current) setError("");
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      await load();
      busyRef.current = false;
      if (alive.current) setBusy(false);
    }
  }
  function type(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const field = e.currentTarget.elements.namedItem(
      "text",
    ) as HTMLInputElement;
    const text = field.value;
    field.value = "";
    void act({ kind: "type", text });
  }
  return (
    <Modal
      title="Your private provider session"
      eyebrow="YOU CONTROL EVERY PAYMENT"
      onClose={onClose}
      wide
    >
      <p className="muted">
        Click a field in the preview, then enter text below. Payment actions are
        sent only when you perform them.
      </p>
      <ErrorBox error={error} />
      <button className="button secondary small" onClick={() => setZoom(!zoom)}>
        {zoom ? "Fit preview to screen" : "Enlarge preview · scroll to move"}
      </button>
      <div className={`provider-viewport ${zoom ? "enlarged" : ""}`}>
        {image ? (
          <img
            className="provider-image"
            src={image}
            alt="Current Shohoz booking session. Click to interact."
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              void act({
                kind: "click",
                x: ((e.clientX - r.left) * 1200) / r.width,
                y: ((e.clientY - r.top) * 850) / r.height,
              });
            }}
          />
        ) : (
          <Spinner label="Opening the provider session…" />
        )}
      </div>
      <form className="provider-input" onSubmit={type}>
        <label>
          Text for the focused field
          <input
            name="text"
            type="password"
            autoComplete="off"
            maxLength={500}
            placeholder="Type securely here"
            required
          />
        </label>
        <button className="button primary" disabled={busy}>
          Send text <ArrowRight size={15} />
        </button>
      </form>
      <div className="button-row provider-controls">
        {["Tab", "Enter", "Backspace", "Escape", "Control+A"].map((key) => (
          <button
            key={key}
            className="button secondary small"
            disabled={busy}
            onClick={() => act({ kind: "key", key })}
          >
            {key}
          </button>
        ))}
        <button
          className="button secondary small"
          disabled={busy}
          aria-label="Scroll provider up"
          onClick={() => act({ kind: "scroll", dy: -500 })}
        >
          <ArrowUp size={15} />
        </button>
        <button
          className="button secondary small"
          disabled={busy}
          aria-label="Scroll provider down"
          onClick={() => act({ kind: "scroll", dy: 500 })}
        >
          <ArrowDown size={15} />
        </button>
        <button
          className="button secondary small"
          disabled={busy}
          onClick={() => load()}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
    </Modal>
  );
}
