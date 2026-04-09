import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Settings2 } from "lucide-react";

/* ─── Types ─── */
interface FinancialEvent {
  id: number;
  date: number; // day of month
  type: "bill" | "insurance" | "investment";
  tag: string;
  title: string;
  subtitle: string;
  amount?: string;
}

/* ─── Data ─── */
const events: FinancialEvent[] = [
  {
    id: 1,
    date: 9,
    type: "bill",
    tag: "💳 CREDIT BILL",
    title: "HDFC Regalia Statement",
    subtitle: "Due by 18:00",
    amount: "₹45,321",
  },
  {
    id: 2,
    date: 9,
    type: "insurance",
    tag: "🛡️ CLAIM UPDATE",
    title: "Virtus GT Bumper Assessment",
    subtitle: "Surveyor assigned for 14:00",
  },
  {
    id: 3,
    date: 9,
    type: "investment",
    tag: "📈 SIP DEDUCTION",
    title: "Axis Bluechip Fund",
    subtitle: "Auto-debit from SBI",
    amount: "₹5,000",
  },
  {
    id: 4,
    date: 15,
    type: "bill",
    tag: "💳 CREDIT BILL",
    title: "ICICI Amazon Pay Statement",
    subtitle: "Due by 23:59",
    amount: "₹12,800",
  },
  {
    id: 5,
    date: 18,
    type: "investment",
    tag: "📈 SIP DEDUCTION",
    title: "Mirae Asset Large Cap",
    subtitle: "Auto-debit from HDFC",
    amount: "₹10,000",
  },
  {
    id: 6,
    date: 22,
    type: "insurance",
    tag: "🛡️ PREMIUM DUE",
    title: "LIC Term Plan Premium",
    subtitle: "Annual renewal",
    amount: "₹24,500",
  },
  {
    id: 7,
    date: 28,
    type: "bill",
    tag: "💳 EMI",
    title: "Car Loan EMI — SBI",
    subtitle: "Auto-debit scheduled",
    amount: "₹18,200",
  },
];

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

  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const isCurrentMonth =
    year === today.getFullYear() && month === today.getMonth();

  /* Build event lookup by date */
  const eventsByDate = useMemo(() => {
    const map: Record<number, FinancialEvent[]> = {};
    events.forEach((e) => {
      if (!map[e.date]) map[e.date] = [];
      map[e.date].push(e);
    });
    return map;
  }, []);

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
                          className={`h-1 w-2.5 rounded-full ${typeColors[ev.type].dot}`}
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
          {selectedEvents.length > 0
            ? `Your Timeline — ${MONTH_NAMES[month]} ${selectedDate}`
            : `Your Timeline — ${MONTH_NAMES[month]} ${selectedDate}`}
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
                <p className="text-3xl mb-2">📅</p>
                <p className="text-sm text-gray-400">
                  No events on this date
                </p>
                <p className="text-[10px] text-gray-500 mt-1">
                  Tap a date with colored markers to see events
                </p>
              </motion.div>
            ) : (
              selectedEvents.map((event, i) => {
                const colors = typeColors[event.type];
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
