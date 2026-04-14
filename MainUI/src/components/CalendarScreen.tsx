import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Settings2, CalendarDays, Loader2 } from "lucide-react";
import { api, CalendarData, CalendarEvent } from "@/lib/api";

/* ─── Style maps ─── */
const typeColors = {
  bill: {
    bg: "bg-[#FF4D4D]/10",
    text: "text-[#FF4D4D]",
    dot: "bg-[#FF4D4D]",
    border: "border-[#FF4D4D]/15",
  },
  insurance: {
    bg: "bg-[#00F0FF]/10",
    text: "text-[#00F0FF]",
    dot: "bg-[#00F0FF]",
    border: "border-[#00F0FF]/15",
  },
  investment: {
    bg: "bg-[#00FF66]/10",
    text: "text-[#00FF66]",
    dot: "bg-[#00FF66]",
    border: "border-[#00FF66]/15",
  },
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/* ─── Helpers ─── */
function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}
function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}
const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/* ─── Component ─── */
const CalendarScreen = () => {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState(today.getDate());
  const [viewMode, setViewMode] = useState<"Day" | "Week" | "Month">("Month");

  const [data, setData] = useState<CalendarData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = localStorage.getItem("astra_user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getCalendar(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[CalendarScreen] API error:", err))
      .finally(() => setLoading(false));
  }, []);

  const events: CalendarEvent[] = data?.events ?? [];

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const isCurrentMonth =
    year === today.getFullYear() && month === today.getMonth();

  /* Build event lookup by date */
  const eventsByDate = useMemo(() => {
    const map: Record<number, CalendarEvent[]> = {};
    events.forEach((e) => {
      if (!map[e.date]) map[e.date] = [];
      map[e.date].push(e);
    });
    return map;
  }, [events]);

  /* Filtered events for selected date */
  const selectedEvents = eventsByDate[selectedDate] ?? [];

  const prevMonth = () => {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
    setSelectedDate(1);
  };

  const nextMonth = () => {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
    setSelectedDate(1);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

  const hasData = data?.has_data ?? false;
  const emptyMessage = data?.message || "No financial events yet. Your bill due dates, SIP debits, and EMIs will appear here automatically.";

  return (
    <div className="min-h-screen pb-28 pt-4 px-4 max-w-lg mx-auto">
      {/* View Mode Toggle + Filter */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-5"
      >
        <div className="flex items-center rounded-full bg-white/5 border border-white/5 p-0.5">
          {(["Day", "Week", "Month"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`relative px-4 py-1.5 text-xs font-semibold rounded-full transition-colors ${
                viewMode === mode
                  ? "bg-[#CCFF00] text-black"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <button className="h-9 w-9 rounded-full bg-white/5 border border-white/5 flex items-center justify-center">
          <Settings2 size={16} className="text-gray-400" />
        </button>
      </motion.div>

      {/* Month Selector */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex items-center justify-center gap-5 mb-5"
      >
        <button
          onClick={prevMonth}
          className="h-8 w-8 rounded-full bg-white/5 border border-white/5 flex items-center justify-center hover:border-[#CCFF00]/30 transition-colors"
        >
          <ChevronLeft size={16} className="text-gray-400" />
        </button>
        <h2 className="font-display text-lg font-bold text-white min-w-[150px] text-center">
          {MONTH_NAMES[month]} {year}
        </h2>
        <button
          onClick={nextMonth}
          className="h-8 w-8 rounded-full bg-white/5 border border-white/5 flex items-center justify-center hover:border-[#CCFF00]/30 transition-colors"
        >
          <ChevronRight size={16} className="text-gray-400" />
        </button>
      </motion.div>

      {/* Calendar Grid */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-3xl bg-[#1E1E1E] border border-white/5 p-4 mb-6"
      >
        {/* Weekday headers */}
        <div className="grid grid-cols-7 gap-1 mb-2">
          {WEEKDAYS.map((day) => (
            <div
              key={day}
              className="text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider py-1"
            >
              {day}
            </div>
          ))}
        </div>

        {/* Date cells */}
        <div className="grid grid-cols-7 gap-1">
          {/* Empty cells before first day */}
          {Array.from({ length: firstDay }).map((_, i) => (
            <div key={`empty-${i}`} className="h-11" />
          ))}

          {/* Actual days */}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const isToday = isCurrentMonth && day === today.getDate();
            const isSelected = day === selectedDate;
            const dayEvents = eventsByDate[day] ?? [];
            const hasEvents = dayEvents.length > 0;

            return (
              <motion.button
                key={day}
                onClick={() => setSelectedDate(day)}
                whileTap={{ scale: 0.9 }}
                className={`relative h-11 flex flex-col items-center justify-center rounded-xl transition-all ${
                  isSelected
                    ? "bg-[#CCFF00]/10 border border-[#CCFF00]/40 shadow-[0_0_12px_rgba(204,255,0,0.15)]"
                    : isToday
                      ? "border border-[#CCFF00] shadow-[0_0_10px_rgba(204,255,0,0.2)]"
                      : "hover:bg-white/5"
                }`}
              >
                <span
                  className={`text-xs font-semibold ${
                    isSelected
                      ? "text-[#CCFF00]"
                      : isToday
                        ? "text-[#CCFF00]"
                        : "text-white"
                  }`}
                >
                  {day}
                </span>

                {/* Event indicator dots */}
                {hasEvents && (
                  <div className="flex gap-0.5 mt-0.5">
                    {dayEvents
                      .slice(0, 3)
                      .map((ev, idx) => (
                        <span
                          key={idx}
                          className={`h-1 w-2.5 rounded-full ${typeColors[ev.type]?.dot || "bg-gray-400"}`}
                        />
                      ))}
                  </div>
                )}
              </motion.button>
            );
          })}
        </div>
      </motion.div>

      {/* Timeline Events */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <h3 className="font-display text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">
          Your Timeline — {MONTH_NAMES[month]} {selectedDate}
        </h3>

        <AnimatePresence mode="wait">
          <motion.div
            key={selectedDate}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-3"
          >
            {selectedEvents.length === 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-2xl bg-[#1E1E1E] border border-white/5 py-10 flex flex-col items-center justify-center"
              >
                {!hasData ? (
                  <>
                    <div className="flex justify-center mb-3">
                      <div className="h-14 w-14 rounded-2xl bg-[#CCFF00]/10 flex items-center justify-center">
                        <CalendarDays size={24} className="text-[#CCFF00]" />
                      </div>
                    </div>
                    <p className="text-sm text-gray-400 text-center px-6">
                      {emptyMessage}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-3xl mb-2">📅</p>
                    <p className="text-sm text-gray-400">
                      No events on this date
                    </p>
                    <p className="text-[10px] text-gray-500 mt-1">
                      Tap a date with colored markers to see events
                    </p>
                  </>
                )}
              </motion.div>
            ) : (
              selectedEvents.map((event, i) => {
                const colors = typeColors[event.type] || typeColors.bill;
                return (
                  <motion.div
                    key={event.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      delay: i * 0.08,
                      type: "spring",
                      stiffness: 300,
                      damping: 25,
                    }}
                    whileTap={{ scale: 0.98 }}
                    className={`rounded-2xl bg-[#1E1E1E] border ${colors.border} p-4 cursor-pointer transition-all hover:border-white/15`}
                  >
                    {/* Tag pill */}
                    <span
                      className={`inline-flex items-center text-[10px] font-bold uppercase tracking-wider rounded-full px-2.5 py-1 mb-3 ${colors.bg} ${colors.text}`}
                    >
                      {event.tag}
                    </span>

                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="font-display text-sm font-bold text-white leading-tight">
                          {event.title}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                          {event.subtitle}
                        </p>
                      </div>
                      {event.amount && (
                        <p className="font-display text-lg font-extrabold text-white shrink-0">
                          {event.amount}
                        </p>
                      )}
                    </div>
                  </motion.div>
                );
              })
            )}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

export default CalendarScreen;
