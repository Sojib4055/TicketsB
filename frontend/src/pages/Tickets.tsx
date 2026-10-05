import { ArrowUpRight, BusFront, Plane, Ship, TrainFront } from "lucide-react";
import { Link } from "react-router-dom";

const services = [
  {
    name: "Bus",
    icon: BusFront,
    tone: "peach",
    url: "https://www.shohoz.com/bus-tickets",
    description:
      "Find your departure, choose available seats, and select a boarding point.",
    detail: "Seat maps · AC & non-AC · Boarding points",
  },
  {
    name: "Train",
    icon: TrainFront,
    tone: "mint",
    url: "https://train.shohoz.com/",
    description:
      "Continue to the railway booking service for routes, classes, and tickets.",
    detail: "Stations · Travel classes · Railway tickets",
  },
  {
    name: "Flights",
    icon: Plane,
    tone: "purple",
    url: "https://www.shohoz.com/air-tickets",
    description:
      "Compare domestic and international flights and review your fare options.",
    detail: "One-way · Return · Multi-city",
  },
  {
    name: "Launch",
    icon: Ship,
    tone: "mint",
    url: "https://www.shohoz.com/launch-tickets/",
    description:
      "Explore waterway departures and choose the accommodation offered for your trip.",
    detail: "Routes · Availability · Launch tickets",
  },
];

export default function Tickets() {
  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ONE TRAVEL DESK. MORE POSSIBILITIES.</p>
          <h1>Every way to get there.</h1>
          <p>Choose how you travel. Continue your booking on Shohoz.</p>
        </div>
      </div>
      <section className="ticket-intro panel" aria-label="How booking works">
        <div>
          <p className="eyebrow">YOUR NEXT JOURNEY</p>
          <h2>Your plans, from road to sky.</h2>
          <p>
            Each option opens the official booking service in a new tab. Sign in
            there to check availability, choose seats where offered, and
            complete payment.
          </p>
        </div>
        <div className="ticket-steps" aria-label="Booking steps">
          <span>
            <b>01</b> Find a departure
          </span>
          <span>
            <b>02</b> Review your selection
          </span>
          <span>
            <b>03</b> Pay on the provider site
          </span>
        </div>
      </section>
      <div className="ticket-services">
        {services.map(
          ({ name, icon: Icon, tone, url, description, detail }) => (
            <article className="ticket-service panel" key={name}>
              <span className={`feature-icon ${tone}`}>
                <Icon size={25} />
              </span>
              <h2>{name}</h2>
              <p>{description}</p>
              <small>{detail}</small>
              <a
                className="button primary"
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Book ${name.toLowerCase()} on Shohoz`}
              >
                Continue to {name === "Train" ? "railway booking" : "Shohoz"}
                <ArrowUpRight size={16} />
              </a>
            </article>
          ),
        )}
      </div>
      <section
        className="ticket-handoff panel"
        aria-label="Your booking and tickets"
      >
        <div>
          <h2>Keep your ticket close.</h2>
          <p>
            Confirmations, tickets, changes, and cancellation requests stay with
            the service where you book. These bookings do not automatically
            appear in My journeys. SeatWatch watches remain separate from
            purchased tickets.
          </p>
        </div>
        <Link to="/" className="button secondary">
          Compare buses here <ArrowUpRight size={16} />
        </Link>
      </section>
    </div>
  );
}
