export type User = { id: string; name: string; email: string };
export type Config = {
  mode: "demo" | "live";
  whatsapp_configured: boolean;
  provider: string;
  timezone: string;
  departure_buffer_minutes: number;
};
export type SearchInput = {
  from_city: string;
  to_city: string;
  journey_date: string;
  seat_count: number;
};
export type Offer = {
  id: string;
  operator: string;
  route: string;
  departure: string;
  arrival: string;
  unit_fare: string;
  seats_available: number;
  service_class: string;
  duration: string;
  boarding_points: string[];
  dropping_points: string[];
  provider_note: string;
  total?: string;
};
export type SearchResult = {
  search_id: string;
  query: SearchInput;
  offers: Offer[];
  checked_at: string;
  expires_in: number;
  booking_enabled: boolean;
};
export type Seat = {
  label: string;
  available: boolean;
  female_only: boolean;
  x: number;
  y: number;
};
export type SeatMap = { seats: Seat[]; message: string; checked_at: string };
export type Passenger = {
  first_name: string;
  last_name: string;
  gender: "male" | "female" | "";
};
export type BookingInput = SearchInput & {
  departure_start: string;
  departure_end: string;
  buy_after: string;
  buy_before: string;
  max_total: string;
  seat_preference: string;
  operators: string[];
  boarding_point: string;
  contact_phone: string;
  contact_email: string;
  whatsapp_phone: string;
  whatsapp_opt_in: boolean;
  low_seat_threshold: number;
  passengers: Passenger[];
  selected_offer_id?: string;
  preferred_seats?: string[];
  monitor_only?: boolean;
  seat_fallback?: "wait" | "any";
  request_key?: string;
};
export type Job = {
  id: string;
  mode: "demo" | "live";
  status: string;
  request: BookingInput;
  data: {
    message?: string;
    total?: string;
    seats?: string[];
    expires_at?: string;
    reference?: string;
    ticket_available?: boolean;
    offers?: Offer[];
    last_checked?: string;
    reservation_attempted?: boolean;
    recovery_required?: boolean;
    preferred_seats_status?: string;
    missing_seats?: string[];
  };
};
export type Alert = {
  id: string;
  kind: string;
  status: string;
  body: string;
  error?: string;
  created: number;
  job_id: string;
};
export type Detail = {
  job: Job;
  events: { message: string; created: number }[];
  session_available: boolean;
  session_recoverable: boolean;
  can_resume: boolean;
};
export type Selection = {
  offer: Offer;
  query: SearchInput;
  seats: string[];
  intent?: "watch" | "prepare";
};
