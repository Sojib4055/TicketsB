import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  BusFront,
  Check,
  Clock3,
  ExternalLink,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useApp } from "../lib/context";
import { api, alertLabel, when } from "../lib/api";
import { Badge, Empty, ErrorBox } from "../components/ui";
export default function Updates({
  connections = false,
}: {
  connections?: boolean;
}) {
  const app = useApp();
  const [filter, setFilter] = useState("all");
  const alerts = app.alerts.filter(
    (a) =>
      filter === "all" ||
      (filter === "delivered"
        ? ["delivered", "read"].includes(a.status)
        : ["failed", "setup_required", "unknown"].includes(a.status)),
  );
  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {connections
              ? "YOUR CONNECTED TRAVEL DESK"
              : "THE LATEST ON YOUR JOURNEY"}
          </p>
          <h1>
            {connections
              ? "Everything, working together."
              : "A little heads-up goes a long way."}
          </h1>
          <p>
            {connections
              ? "Know what’s connected and what’s ready for your next trip."
              : "Availability updates, timely reminders, and one less thing to think about."}
          </p>
        </div>
      </div>
      {connections ? (
        <>
          <div className="connections-grid">
            <article className="connection panel">
              <div className="connection-top">
                <span className="feature-icon purple">
                  <BusFront size={25} />
                </span>
                <Badge tone="green">Live search available</Badge>
              </div>
              <h2>Shohoz</h2>
              <p>
                Discover current routes, compare fares, and check how many seats
                are available on your preferred departure.
              </p>
              <div className="connection-status">
                <span>Public bus search</span>
                <strong>
                  <Check size={15} /> Connected
                </strong>
              </div>
              <div className="connection-status">
                <span>Automatic reservations</span>
                <Badge tone={app.config?.mode === "live" ? "green" : "amber"}>
                  {app.config?.mode === "live" ? "Live enabled" : "Demo mode"}
                </Badge>
              </div>
              <p className="connection-note">
                Shohoz may require sign-in or verification to open seat maps and
                continue a booking.
              </p>
              <a
                className="button secondary"
                href="https://www.shohoz.com/bus-tickets/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Visit Shohoz <ExternalLink size={15} />
              </a>
            </article>
            <article className="connection panel">
              <div className="connection-top">
                <span className="feature-icon mint">
                  <MessageCircle size={25} />
                </span>
                <Badge
                  tone={app.config?.whatsapp_configured ? "green" : "amber"}
                >
                  {app.config?.whatsapp_configured
                    ? "Configured"
                    : "Setup required"}
                </Badge>
              </div>
              <h2>WhatsApp Business</h2>
              <p>
                Seat availability, payment reminders, and booking updates,
                delivered to the number you choose.
              </p>
              <div className="connection-status">
                <span>Message delivery</span>
                <strong>
                  {app.config?.whatsapp_configured
                    ? "Ready for opted-in journeys"
                    : "Awaiting connection"}
                </strong>
              </div>
              <div className="connection-status">
                <span>Your consent</span>
                <strong>Per journey</strong>
              </div>
              <p className="connection-note">
                {app.config?.whatsapp_configured
                  ? "Delivery receipts show when messages are accepted, delivered, or read."
                  : "The site operator needs to connect a WhatsApp Business account and an approved message template. Alerts remain available in your workspace."}
              </p>
              <Link to="/alerts" className="button secondary">
                View notifications <ArrowRight size={15} />
              </Link>
            </article>
          </div>
          <section className="privacy-panel">
            <ShieldCheck size={31} />
            <div>
              <h3>A few things should always stay yours.</h3>
              <p>
                Your passenger details stay in your private account. Each
                booking has a separate provider session, and every payment is
                completed by you.
              </p>
            </div>
            <Badge tone="purple">Payment is manual</Badge>
          </section>
          {app.user && <AccountRecovery />}
        </>
      ) : (
        <>
          <div className="notification-banner">
            <span className="feature-icon mint">
              <MessageCircle size={28} />
            </span>
            <div>
              <h3>Keep your plans close. Your updates closer.</h3>
              <p>
                {app.config?.whatsapp_configured
                  ? "WhatsApp is configured. Opt in when creating a journey to receive its updates."
                  : "Your updates live here. Connect WhatsApp to have them delivered to your phone, too."}
              </p>
            </div>
            <Link to="/connections" className="button secondary small">
              Connections <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="section-toolbar">
            <div className="tabs">
              {[
                ["all", "All updates"],
                ["delivered", "Delivered"],
                ["attention", "Needs attention"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  className={filter === value ? "active" : ""}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="muted">{alerts.length} updates</span>
          </div>
          <ErrorBox error={app.jobsError} retry={app.refresh} />
          {!alerts.length ? (
            <div className="panel">
              <Empty
                icon={<Bell size={27} />}
                title={
                  app.user
                    ? "You’re all caught up."
                    : "Your updates deserve a home."
                }
                action={
                  <button
                    className="button primary"
                    onClick={() =>
                      app.user ? app.plan() : app.setAuthOpen(true)
                    }
                  >
                    {app.user ? "Plan a journey" : "Sign in to see updates"}
                    <ArrowRight size={16} />
                  </button>
                }
              >
                Your seat alerts and booking reminders will appear here, with
                their delivery status.
              </Empty>
            </div>
          ) : (
            <div className="alerts-list">
              {alerts.map((a) => (
                <article className="alert-row panel" key={a.id}>
                  <span
                    className={`feature-icon ${a.kind.includes("payment") ? "peach" : "purple"}`}
                  >
                    {a.kind.includes("payment") ? (
                      <Clock3 size={20} />
                    ) : (
                      <Bell size={20} />
                    )}
                  </span>
                  <div>
                    <div className="alert-row-heading">
                      <h3>{a.kind.replaceAll("_", " ")}</h3>
                      <Badge
                        tone={
                          ["delivered", "read"].includes(a.status)
                            ? "green"
                            : "amber"
                        }
                      >
                        {alertLabel[a.status] || a.status}
                      </Badge>
                    </div>
                    <p>{a.body}</p>
                    {a.error && <ErrorBox error={a.error} />}
                    <div className="alert-footer">
                      <span>{when(a.created)}</span>
                      <Link to={`/journeys?job=${a.job_id}`}>
                        View journey <ArrowUpRight size={13} />
                      </Link>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
function AccountRecovery() {
  const app = useApp();
  const recovery = useMutation({
    mutationFn: (password: string) =>
      api<{ code: string; message: string }>("/api/auth/recovery-code", {
        password,
      }),
  });
  return (
    <section className="panel recovery-panel">
      <h2>Keep a way back into your account.</h2>
      <p className="muted">
        Save a recovery code offline to reset your password if you forget it.
        Generating a new code replaces the old one.
      </p>
      <form
        className="provider-input"
        onSubmit={(e) => {
          e.preventDefault();
          const field = e.currentTarget.elements.namedItem(
            "password",
          ) as HTMLInputElement;
          recovery.mutate(field.value);
          field.value = "";
        }}
      >
        <label>
          Current password
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            minLength={12}
            maxLength={200}
          />
        </label>
        <button className="button secondary" disabled={recovery.isPending}>
          Generate recovery code
        </button>
      </form>
      <ErrorBox error={recovery.error} />
      {recovery.data && (
        <div className="recovery-result" role="status">
          <p>{recovery.data.message}</p>
          <label>
            Your recovery code
            <input
              readOnly
              value={recovery.data.code}
              onFocus={(e) => e.target.select()}
            />
          </label>
          <button
            className="button secondary small"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(recovery.data!.code);
                app.notify("Recovery code copied. Store it somewhere private.");
              } catch {
                app.notify("Select the code above and copy it manually.");
              }
            }}
          >
            Copy recovery code
          </button>
        </div>
      )}
    </section>
  );
}
