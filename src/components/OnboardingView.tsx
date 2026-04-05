import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import AstraLogo from "./AstraLogo";

interface Props {
  onComplete: () => void;
}

const steps = [
  "Verifying mobile number...",
  "Fetching SBI Profile...",
  "Linking HDFC Savings...",
  "Syncing Credit Score...",
  "Success! Welcome aboard.",
];

const OnboardingView = ({ onComplete }: Props) => {
  const [phone, setPhone] = useState("");
  const [linking, setLinking] = useState(false);
  const [stepIdx, setStepIdx] = useState(-1);

  const handleLink = () => {
    if (phone.length < 10) return;
    setLinking(true);
    setStepIdx(0);

    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i < steps.length) {
        setStepIdx(i);
      } else {
        clearInterval(interval);
        setTimeout(onComplete, 600);
      }
    }, 900);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="flex w-full max-w-sm flex-col items-center gap-8"
      >
        <AstraLogo size={56} />

        <div className="text-center">
          <h1 className="font-display text-3xl font-bold tracking-tight text-foreground">
            Astra <span className="text-gradient-teal">360</span>
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Your AI Financial Guardian
          </p>
        </div>

        <AnimatePresence mode="wait">
          {!linking ? (
            <motion.div
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex w-full flex-col gap-4"
            >
              <div className="glass rounded-xl p-1">
                <div className="flex items-center gap-2 rounded-lg bg-secondary/50 px-4 py-3">
                  <span className="text-muted-foreground text-sm font-medium">+91</span>
                  <input
                    type="tel"
                    maxLength={10}
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                    placeholder="Enter mobile number"
                    className="flex-1 bg-transparent text-foreground placeholder:text-muted-foreground/50 outline-none text-sm"
                  />
                </div>
              </div>

              <button
                onClick={handleLink}
                disabled={phone.length < 10}
                className="gradient-teal rounded-xl px-6 py-3.5 font-display font-semibold text-primary-foreground transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed teal-glow"
              >
                Link Accounts
              </button>
            </motion.div>
          ) : (
            <motion.div
              key="progress"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex w-full flex-col items-center gap-4"
            >
              {steps.map((step, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={i <= stepIdx ? { opacity: 1, x: 0 } : { opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className={`flex w-full items-center gap-3 rounded-lg px-4 py-2.5 text-sm ${
                    i === stepIdx
                      ? "text-primary font-medium"
                      : i < stepIdx
                      ? "text-muted-foreground"
                      : "text-muted-foreground/30"
                  }`}
                >
                  <div
                    className={`h-2 w-2 rounded-full transition-colors ${
                      i <= stepIdx ? "bg-primary" : "bg-muted"
                    }`}
                  />
                  {step}
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

export default OnboardingView;
