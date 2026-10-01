import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./api";
import type { Alert, Config, Job, Selection, User } from "./types";
import { Toast } from "../components/ui";

type AppContext = {
  user: User | null;
  config?: Config;
  jobs: Job[];
  alerts: Alert[];
  connected: boolean;
  initError: Error | null;
  jobsError: Error | null;
  loading: boolean;
  theme: string;
  toggleTheme: () => void;
  notify: (message: string) => void;
  authOpen: boolean;
  setAuthOpen: (value: boolean) => void;
  booking: Selection | "general" | null;
  setBooking: (value: Selection | "general" | null) => void;
  plan: (selection?: Selection) => void;
  signedIn: (user: User) => void;
  logout: () => Promise<void>;
  refresh: () => void;
};
const Context = createContext<AppContext | null>(null);
export function AppProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const account = useQuery({
    queryKey: ["account"],
    queryFn: ({ signal }) =>
      api<{ user: User | null }>("/api/auth/me", undefined, signal),
    staleTime: 60000,
  });
  const settings = useQuery({
    queryKey: ["config"],
    queryFn: ({ signal }) => api<Config>("/api/status", undefined, signal),
    staleTime: 60000,
  });
  const user = account.data?.user ?? null;
  const trips = useQuery({
    queryKey: ["jobs", user?.id],
    queryFn: ({ signal }) =>
      api<{ jobs: Job[]; alerts: Alert[] }>("/api/jobs", undefined, signal),
    enabled: !!user,
    refetchInterval: 5000,
    retry: (count, error) =>
      !(error instanceof ApiError && error.status === 401) && count < 1,
  });
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem("seatwatch-theme") || "light";
    } catch {
      return "light";
    }
  });
  const [message, notify] = useState("");
  const dismiss = useCallback(() => notify(""), []);
  const [authOpen, setAuthOpen] = useState(false);
  const [booking, setBooking] = useState<Selection | "general" | null>(null);
  const [pending, setPending] = useState<Selection | "general" | null>(null);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("seatwatch-theme", theme);
    } catch {
      /* Storage may be disabled. */
    }
  }, [theme]);
  useEffect(() => {
    if (trips.error instanceof ApiError && trips.error.status === 401) {
      client.setQueryData(["account"], { user: null });
      client.removeQueries({ queryKey: ["jobs"] });
      client.removeQueries({ queryKey: ["detail"] });
      setBooking(null);
      notify("Your session expired. Sign in to continue.");
    }
  }, [trips.error, client]);
  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ["jobs"] });
    void client.invalidateQueries({ queryKey: ["detail"] });
  }, [client]);
  function plan(selection?: Selection) {
    if (user) setBooking(selection || "general");
    else {
      setPending(selection || "general");
      setAuthOpen(true);
    }
  }
  function signedIn(next: User) {
    client.setQueryData(["account"], { user: next });
    setAuthOpen(false);
    if (pending) {
      setBooking(pending);
      setPending(null);
    }
    notify(`Welcome, ${next.name.split(" ")[0]}. Your travel desk is ready.`);
  }
  async function logout() {
    try {
      await api("/api/auth/logout", {});
      await client.cancelQueries({ queryKey: ["jobs"] });
      await client.cancelQueries({ queryKey: ["detail"] });
      client.setQueryData(["account"], { user: null });
      client.removeQueries({ queryKey: ["jobs"] });
      client.removeQueries({ queryKey: ["detail"] });
      setBooking(null);
      notify("You’ve signed out.");
    } catch (error) {
      notify((error as Error).message);
    }
  }
  return (
    <Context.Provider
      value={{
        user,
        config: settings.data,
        jobs: trips.data?.jobs || [],
        alerts: trips.data?.alerts || [],
        connected: !account.isError && !settings.isError && !trips.isError,
        initError: account.error || settings.error,
        jobsError: trips.error,
        loading: account.isPending || settings.isPending,
        theme,
        toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
        notify,
        authOpen,
        setAuthOpen: (value) => {
          setAuthOpen(value);
          if (!value) setPending(null);
        },
        booking,
        setBooking,
        plan,
        signedIn,
        logout,
        refresh,
      }}
    >
      {children}
      {message && <Toast message={message} dismiss={dismiss} />}
    </Context.Provider>
  );
}
export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("App provider missing");
  return value;
}
