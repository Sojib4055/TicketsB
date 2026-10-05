import { lazy, Suspense, useEffect, useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  ArrowUpRight,
  Bell,
  BusFront,
  ChevronRight,
  CircleHelp,
  Compass,
  Globe2,
  LogOut,
  Menu,
  MessageCircle,
  Moon,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Ticket,
  X,
} from "lucide-react";
import { useApp } from "./lib/context";
import { Badge, ErrorBox, Modal, Spinner } from "./components/ui";
import { AuthDialog, BookingDialog } from "./components/Booking";
import SearchPage from "./pages/Search";
const Journeys = lazy(() => import("./pages/Journeys"));
const Updates = lazy(() => import("./pages/Updates"));
const Tickets = lazy(() => import("./pages/Tickets"));
const nav = [
  { to: "/tickets", label: "Book tickets", icon: BusFront },
  { to: "/", label: "Explore buses", icon: Compass },
  { to: "/journeys", label: "My journeys", icon: Ticket },
  { to: "/alerts", label: "Notifications", icon: Bell },
  { to: "/connections", label: "Connections", icon: SlidersHorizontal },
];
export default function App() {
  const app = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState(false);
  const [compact, setCompact] = useState(
    () => window.matchMedia("(max-width: 780px)").matches,
  );
  const [help, setHelp] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 780px)");
    const update = () => {
      setCompact(media.matches);
      if (!media.matches) setMobile(false);
    };
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!mobile || !compact) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.querySelector<HTMLButtonElement>(".mobile-close")?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobile(false);
      }
      if (event.key !== "Tab") return;
      const controls = [
        ...document.querySelectorAll<HTMLElement>(
          ".sidebar a, .sidebar button",
        ),
      ].filter((el) => el.getClientRects().length);
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [mobile, compact]);
  const active = app.jobs.filter((j) =>
    ["MONITORING", "SCHEDULED", "PREPARING"].includes(j.status),
  ).length;
  useEffect(() => {
    setMobile(false);
    document.title = `${nav.find((n) => n.to === location.pathname)?.label || "Travel desk"} · SeatWatch`;
  }, [location.pathname]);
  useEffect(() => {
    const job = new URLSearchParams(window.location.search).get("job");
    if (job)
      navigate(`/journeys?job=${encodeURIComponent(job)}`, { replace: true });
  }, [navigate]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      {mobile && (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        className={`sidebar ${mobile ? "is-open" : ""}`}
        inert={compact && !mobile}
        aria-label="Workspace navigation"
      >
        <NavLink to="/" className="brand" onClick={() => setMobile(false)}>
          <span className="brand-mark">
            <BusFront size={23} />
          </span>
          <span>
            seatwatch<span className="brand-dot">.</span>
            <small>THE JOURNEY STARTS HERE</small>
          </span>
        </NavLink>
        <button
          className="mobile-close icon-button"
          onClick={() => setMobile(false)}
          aria-label="Close menu"
        >
          <X />
        </button>
        <p className="nav-label">YOUR WORKSPACE</p>
        <nav aria-label="Main navigation">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              end={to === "/"}
              key={to}
              to={to}
              onClick={() => setMobile(false)}
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
            >
              <Icon size={19} />
              <span>{label}</span>
              {to === "/journeys" && active > 0 && <small>{active}</small>}
              {to === "/alerts" && app.alerts.length > 0 && (
                <i className="notification-dot" />
              )}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-watch">
          <div className="sidebar-watch-icon">
            <MessageCircle size={23} />
            <i />
          </div>
          <h3>Your seat. Your moment.</h3>
          <p>Get a heads-up when seats run low. Let the journey come to you.</p>
          <button onClick={() => navigate("/alerts")}>
            Explore alerts <ArrowUpRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button
            className="nav-item"
            onClick={() => {
              setMobile(false);
              setHelp(true);
            }}
          >
            <CircleHelp size={19} />
            <span>How it works</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="sidebar-divider" />
          {app.user ? (
            <div className="user-profile">
              <span className="avatar">
                {app.user.name.slice(0, 2).toUpperCase()}
              </span>
              <div>
                <strong>{app.user.name}</strong>
                <small>Personal workspace</small>
              </div>
              <button
                className="icon-button"
                aria-label="Sign out"
                onClick={async () => {
                  await app.logout();
                  setMobile(false);
                }}
              >
                <LogOut size={17} />
              </button>
            </div>
          ) : (
            <button
              className="sidebar-signin"
              onClick={() => {
                setMobile(false);
                app.setAuthOpen(true);
              }}
            >
              <span className="avatar">
                <Plus size={18} />
              </span>
              <span>
                <strong>Make it your journey</strong>
                <small>Sign in or create an account</small>
              </span>
              <ChevronRight size={16} />
            </button>
          )}
          <p className="sidebar-footnote">
            <span className={`status-dot ${app.connected ? "" : "offline"}`} />
            {app.connected
              ? "Your travel desk is connected"
              : "Reconnecting to your travel desk"}
          </p>
        </div>
      </aside>
      <div className="workspace" inert={compact && mobile}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button menu-button"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {nav.find((n) => n.to === location.pathname)?.label ||
                "Explore buses"}
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="locale">
              <Globe2 size={15} /> Bangladesh <span>·</span> BDT
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label={`Switch to ${app.theme === "light" ? "dark" : "light"} theme`}
              onClick={app.toggleTheme}
            >
              {app.theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <NavLink
              to="/alerts"
              className="icon-button bell-button"
              aria-label="View notifications"
            >
              <Bell size={19} />
              {app.alerts.length > 0 && <i />}
            </NavLink>
            {!app.user && (
              <button
                className="button small primary"
                onClick={() => app.setAuthOpen(true)}
              >
                Sign in <ArrowUpRight size={14} />
              </button>
            )}
          </div>
        </header>
        <main id="main" className="page-content" tabIndex={-1}>
          <ErrorBox
            error={app.initError}
            retry={() => window.location.reload()}
          />
          <Suspense
            fallback={
              <div className="page-loader">
                <Spinner label="Opening your workspace…" />
              </div>
            }
          >
            <Routes>
              <Route path="/tickets" element={<Tickets />} />
              <Route path="/" element={<SearchPage />} />
              <Route path="/journeys" element={<Journeys />} />
              <Route path="/alerts" element={<Updates />} />
              <Route path="/connections" element={<Updates connections />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
          <footer className="page-footer">
            <span>Thoughtfully built for journeys in Bangladesh.</span>
            <span>
              <ShieldCheck size={14} /> Your payment, always in your hands.
            </span>
          </footer>
        </main>
      </div>
      {app.authOpen && <AuthDialog />}
      {app.booking && app.user && app.config && <BookingDialog />}
      {help && (
        <Modal
          title="A little planning. A lot less waiting."
          eyebrow="WELCOME TO SEATWATCH"
          onClose={() => setHelp(false)}
        >
          <div className="help-steps">
            {[
              [
                Search,
                "Find your departure",
                "Search live Shohoz buses, compare fares, and choose a route that suits you.",
              ],
              [
                Bell,
                "Let us keep watch",
                "Save a departure and set your time window and budget. Availability updates appear in your workspace.",
              ],
              [
                ShieldCheck,
                "Stay in control",
                "Review prepared bookings and complete payment yourself. Live reservations and WhatsApp need operator setup.",
              ],
            ].map(([Icon, title, text], i) => {
              const Symbol = Icon as typeof Search;
              return (
                <div key={i}>
                  <span className="feature-icon">
                    <Symbol size={22} />
                  </span>
                  <section>
                    <h3>{String(title)}</h3>
                    <p>{String(text)}</p>
                  </section>
                </div>
              );
            })}
          </div>
          <Badge tone="purple">All journey times use Asia/Dhaka</Badge>
        </Modal>
      )}
    </div>
  );
}
