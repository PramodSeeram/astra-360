import { motion, AnimatePresence } from "framer-motion";
import { ShieldAlert, X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: (action: "freeze" | "approve") => void;
}

const ScamAlertModal = ({ open, onClose }: Props) => (
  <AnimatePresence>
    {open && (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-background/80 backdrop-blur-md" />

        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.9, opacity: 0 }}
          transition={{ type: "spring", stiffness: 350, damping: 25 }}
          className="relative w-full max-w-sm rounded-2xl border border-danger/30 bg-card p-6"
          style={{ boxShadow: "0 0 40px hsl(0 72% 55% / 0.2)" }}
        >
          <button
            onClick={() => onClose("approve")}
            className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
          >
            <X size={18} />
          </button>

          <div className="flex flex-col items-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-danger/15">
              <ShieldAlert size={28} className="text-danger" />
            </div>

            <div>
              <h2 className="font-display text-xl font-bold text-foreground">
                ⚠️ Suspicious Transaction
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                A potentially fraudulent transaction was detected.
              </p>
            </div>

            <div className="w-full space-y-2 rounded-xl bg-secondary/50 p-4 text-left text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Merchant</span>
                <span className="font-medium text-foreground">AMAZON US</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Amount</span>
                <span className="font-medium text-danger">₹20,000</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <span className="font-medium text-warning">Anomaly detected</span>
              </div>
            </div>

            <div className="flex w-full flex-col gap-2 pt-2">
              <button
                onClick={() => onClose("freeze")}
                className="w-full rounded-xl bg-danger px-4 py-3 font-display font-semibold text-danger-foreground transition-all hover:opacity-90 active:scale-[0.98]"
              >
                No, Freeze Account
              </button>
              <button
                onClick={() => onClose("approve")}
                className="w-full rounded-xl border border-border px-4 py-3 font-display font-medium text-foreground transition-all hover:bg-secondary active:scale-[0.98]"
              >
                It Was Me
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    )}
  </AnimatePresence>
);

export default ScamAlertModal;
