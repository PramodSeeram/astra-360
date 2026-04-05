import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Building2, CreditCard, Search, FileText, ShieldCheck, CheckCircle2 } from "lucide-react";
import AstraLogo from "./AstraLogo";

interface Props {
  onComplete: () => void;
}

const steps = [
  {
    label: "Verifying Identity",
    icon: ShieldCheck,
    description: "Authenticating your mobile number",
  },
  {
    label: "Fetching Bank Accounts",
    icon: Building2,
    description: "Scanning SBI, HDFC linked accounts",
  },
  {
    label: "Checking CIBIL Score",
    icon: CreditCard,
    description: "Pulling credit bureau report",
  },
  {
    label: "Scanning Documents",
    icon: FileText,
    description: "Analysing loans, FDs & investments",
  },
  {
    label: "All Set!",
    icon: CheckCircle2,
    description: "Your financial profile is ready",
  },
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
        setTimeout(onComplete, 800);
      }
    }, 1200);
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
              className="flex w-full flex-col items-center gap-3"
            >
              {/* Scanning visual */}
              <div className="relative mb-4">
                {/* Icon orbit ring */}
                <div className="relative h-40 w-40">
                  {steps.slice(0, -1).map((step, i) => {
                    const angle = (i / 4) * Math.PI * 2 - Math.PI / 2;
                    const x = Math.cos(angle) * 58;
                    const y = Math.sin(angle) * 58;
                    const isActive = i === stepIdx;
                    const isDone = i < stepIdx;
                    const Icon = step.icon;

                    return (
                      <motion.div
                        key={i}
                        className="absolute"
                        style={{
                          left: `calc(50% + ${x}px - 20px)`,
                          top: `calc(50% + ${y}px - 20px)`,
                        }}
                        initial={{ opacity: 0, scale: 0 }}
                        animate={{
                          opacity: 1,
                          scale: isActive ? 1.2 : 1,
                        }}
                        transition={{ delay: 0.1 + i * 0.1, type: "spring", stiffness: 300 }}
                      >
                        <div
                          className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-500 ${
                            isActive
                              ? "bg-primary/20 ring-2 ring-primary shadow-lg shadow-primary/30"
                              : isDone
                              ? "bg-primary/10"
                              : "bg-muted/30"
                          }`}
                        >
                          {isDone ? (
                            <CheckCircle2 size={18} className="text-primary" />
                          ) : (
                            <Icon
                              size={18}
                              className={
                                isActive ? "text-primary" : "text-muted-foreground/50"
                              }
                            />
                          )}
                        </div>
                      </motion.div>
                    );
                  })}

                  {/* Center magnifying glass / scanner */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <motion.div
                      animate={{
                        rotate: stepIdx * 90,
                      }}
                      transition={{ type: "spring", stiffness: 80, damping: 15 }}
                    >
                      <motion.div
                        animate={{
                          scale: [1, 1.15, 1],
                        }}
                        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                        className="flex h-14 w-14 items-center justify-center rounded-2xl glass border border-primary/30"
                      >
                        <Search size={24} className="text-primary" />
                      </motion.div>
                    </motion.div>
                  </div>

                  {/* Scanning ring pulse */}
                  {stepIdx < steps.length - 1 && (
                    <motion.div
                      className="absolute inset-0 rounded-full border-2 border-primary/20"
                      animate={{ scale: [0.85, 1.1, 0.85], opacity: [0.5, 0.15, 0.5] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    />
                  )}
                </div>
              </div>

              {/* Current step text */}
              <AnimatePresence mode="wait">
                <motion.div
                  key={stepIdx}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.3 }}
                  className="text-center"
                >
                  <p className="font-display text-base font-semibold text-foreground">
                    {steps[stepIdx]?.label}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {steps[stepIdx]?.description}
                  </p>
                </motion.div>
              </AnimatePresence>

              {/* Progress dots */}
              <div className="flex gap-2 mt-3">
                {steps.map((_, i) => (
                  <motion.div
                    key={i}
                    className={`h-1.5 rounded-full transition-all duration-500 ${
                      i <= stepIdx ? "bg-primary" : "bg-muted/40"
                    }`}
                    animate={{ width: i === stepIdx ? 24 : 6 }}
                    transition={{ type: "spring", stiffness: 300, damping: 25 }}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
};

export default OnboardingView;
