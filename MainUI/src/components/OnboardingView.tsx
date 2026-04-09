import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ShieldCheck, Zap, Check, Building2, CreditCard, Search, FileText, CheckCircle2 } from "lucide-react";
import AstraLogo from "./AstraLogo";

interface Props {
  onComplete: () => void;
}

const slides = [
  {
    icon: Sparkles,
    heading: "Your AI Financial Co-Pilot.",
    subtitle: "Astra 360 proactively tracks your transactions, bills, and investments in real-time.",
  },
  {
    icon: ShieldCheck,
    heading: "Scam & Fraud Guardian.",
    subtitle: "Real-time threat analysis protects your accounts from unauthorized and suspicious activities.",
  },
  {
    icon: Zap,
    heading: "Smart Spend & Bill Insights.",
    subtitle: "Get automated predictions on your monthly spends, subscriptions, and credit health.",
  },
];

const scanSteps = [
  { label: "Verifying Identity", icon: ShieldCheck, description: "Authenticating your mobile number" },
  { label: "Fetching Bank Accounts", icon: Building2, description: "Scanning SBI, HDFC linked accounts" },
  { label: "Checking CIBIL Score", icon: CreditCard, description: "Pulling credit bureau report" },
  { label: "Scanning Documents", icon: FileText, description: "Analysing loans, FDs & investments" },
  { label: "All Set!", icon: CheckCircle2, description: "Your financial profile is ready" },
];

const OnboardingView = ({ onComplete }: Props) => {
  const [stage, setStage] = useState<"carousel" | "otp" | "scanning">("carousel");
  const [slideIdx, setSlideIdx] = useState(0);
  const [phone, setPhone] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [stepIdx, setStepIdx] = useState(-1);

  const nextSlide = () => {
    if (slideIdx < slides.length - 1) setSlideIdx(slideIdx + 1);
    else setStage("otp");
  };

  const handleAgree = () => {
    if (phone.length < 10 || !agreed) return;
    setStage("scanning");
    setStepIdx(0);
    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i < scanSteps.length) setStepIdx(i);
      else {
        clearInterval(interval);
        setTimeout(onComplete, 800);
      }
    }, 1200);
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 bg-background">
      <AnimatePresence mode="wait">
        {stage === "carousel" && (
          <motion.div
            key="carousel"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, x: -30 }}
            className="flex w-full max-w-sm flex-col items-center"
          >
            {/* Icon */}
            <AnimatePresence mode="wait">
              <motion.div
                key={slideIdx}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.4 }}
                className="mb-12"
              >
                {(() => {
                  const Icon = slides[slideIdx].icon;
                  return (
                    <div className="flex h-24 w-24 items-center justify-center rounded-3xl bg-card border border-border/30">
                      <Icon size={40} className="text-primary" strokeWidth={1.5} />
                    </div>
                  );
                })()}
              </motion.div>
            </AnimatePresence>

            {/* Text */}
            <AnimatePresence mode="wait">
              <motion.div
                key={slideIdx}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.35 }}
                className="text-center mb-16"
              >
                <h1 className="font-display text-3xl font-bold text-foreground mb-3 leading-tight">
                  {slides[slideIdx].heading}
                </h1>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {slides[slideIdx].subtitle}
                </p>
              </motion.div>
            </AnimatePresence>

            {/* Progress dots */}
            <div className="flex items-center gap-2 mb-6">
              {slides.map((_, i) => (
                <motion.div
                  key={i}
                  className={`h-1 rounded-full transition-all duration-300 ${
                    i <= slideIdx ? "bg-primary" : "bg-border"
                  }`}
                  animate={{ width: i === slideIdx ? 28 : 8 }}
                />
              ))}
            </div>

            {/* Button */}
            <button
              onClick={nextSlide}
              className="w-full rounded-2xl border border-primary/40 px-6 py-4 font-display font-semibold text-primary text-sm tracking-wide transition-all hover:bg-primary/10 active:scale-[0.98]"
            >
              {slideIdx < slides.length - 1 ? "Next" : "Become a Member"}
            </button>
          </motion.div>
        )}

        {stage === "otp" && (
          <motion.div
            key="otp"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            className="flex w-full max-w-sm flex-col"
          >
            <AstraLogo size={40} />
            <h1 className="font-display text-2xl font-bold text-foreground mt-6 mb-2">
              Give us your mobile number
            </h1>
            <p className="text-sm text-muted-foreground mb-8">
              To apply, we need your mobile number linked to your credit cards.
            </p>

            {/* Phone input */}
            <div className="rounded-2xl border border-border bg-card px-4 py-3.5 mb-4 focus-within:border-primary transition-colors">
              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-sm font-medium">+91</span>
                <input
                  type="tel"
                  maxLength={10}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
                  placeholder="Enter mobile number"
                  className="flex-1 bg-transparent text-foreground placeholder:text-muted-foreground/40 outline-none text-sm"
                />
              </div>
            </div>

            {/* Checkbox */}
            <label className="flex items-start gap-3 mb-8 cursor-pointer">
              <button
                onClick={() => setAgreed(!agreed)}
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all ${
                  agreed
                    ? "bg-primary border-primary"
                    : "border-border bg-transparent"
                }`}
              >
                {agreed && <Check size={12} className="text-primary-foreground" />}
              </button>
              <span className="text-xs text-muted-foreground leading-relaxed">
                You agree to allow Astra 360 to check your credit information with RBI approved credit bureaus.
              </span>
            </label>

            {/* Button */}
            <button
              onClick={handleAgree}
              disabled={phone.length < 10 || !agreed}
              className="w-full rounded-2xl bg-primary px-6 py-4 font-display font-semibold text-primary-foreground text-sm transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Agree & Continue
            </button>
          </motion.div>
        )}

        {stage === "scanning" && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex w-full max-w-sm flex-col items-center gap-3"
          >
            {/* Scanning visual */}
            <div className="relative mb-4">
              <div className="relative h-40 w-40">
                {scanSteps.slice(0, -1).map((step, i) => {
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
                      animate={{ opacity: 1, scale: isActive ? 1.2 : 1 }}
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
                          <Icon size={18} className={isActive ? "text-primary" : "text-muted-foreground/50"} />
                        )}
                      </div>
                    </motion.div>
                  );
                })}

                <div className="absolute inset-0 flex items-center justify-center">
                  <motion.div animate={{ rotate: stepIdx * 90 }} transition={{ type: "spring", stiffness: 80, damping: 15 }}>
                    <motion.div
                      animate={{ scale: [1, 1.15, 1] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                      className="flex h-14 w-14 items-center justify-center rounded-2xl bg-card border border-primary/30"
                    >
                      <Search size={24} className="text-primary" />
                    </motion.div>
                  </motion.div>
                </div>

                {stepIdx < scanSteps.length - 1 && (
                  <motion.div
                    className="absolute inset-0 rounded-full border-2 border-primary/20"
                    animate={{ scale: [0.85, 1.1, 0.85], opacity: [0.5, 0.15, 0.5] }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                  />
                )}
              </div>
            </div>

            <AnimatePresence mode="wait">
              <motion.div
                key={stepIdx}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="text-center"
              >
                <p className="font-display text-base font-semibold text-foreground">
                  {scanSteps[stepIdx]?.label}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {scanSteps[stepIdx]?.description}
                </p>
              </motion.div>
            </AnimatePresence>

            <div className="flex gap-2 mt-3">
              {scanSteps.map((_, i) => (
                <motion.div
                  key={i}
                  className={`h-1.5 rounded-full transition-all duration-500 ${
                    i <= stepIdx ? "bg-primary" : "bg-muted/40"
                  }`}
                  animate={{ width: i === stepIdx ? 24 : 6 }}
                />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default OnboardingView;
