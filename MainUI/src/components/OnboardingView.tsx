import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ShieldCheck, Zap, Check, Building2, CreditCard, Search, FileText, CheckCircle2, Loader2, ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import AstraLogo from "./AstraLogo";
import { api } from "@/lib/api";

interface Props {
  onComplete: (userId: string) => void;
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

type Stage = "carousel" | "mobile" | "otp_verify" | "kyc" | "scanning";

const OnboardingView = ({ onComplete }: Props) => {
  const [stage, setStage] = useState<Stage>("carousel");
  const [slideIdx, setSlideIdx] = useState(0);
  const [phone, setPhone] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [stepIdx, setStepIdx] = useState(-1);
  const [loading, setLoading] = useState(false);

  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [devOtp, setDevOtp] = useState("");
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  const [userId, setUserId] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [pan, setPan] = useState("");
  const [panType, setPanType] = useState("");

  const [scanApiDone, setScanApiDone] = useState(false);
  const [scanAnimDone, setScanAnimDone] = useState(false);

  const nextSlide = () => {
    if (slideIdx < slides.length - 1) setSlideIdx(slideIdx + 1);
    else setStage("mobile");
  };

  const handleAgree = async () => {
    if (phone.length < 10 || !agreed) return;
    setLoading(true);
    try {
      const res = await api.sendOtp(phone);
      if (res.dev_otp) {
        setDevOtp(res.dev_otp);
      }
      toast.success("OTP sent successfully!");
      setStage("otp_verify");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to send OTP";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index: number, value: string) => {
    if (!/^\d*$/.test(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);
    if (value && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const handleAutoFill = () => {
    if (!devOtp) return;
    const digits = devOtp.split("");
    setOtp(digits);
  };

  const handleVerifyOtp = async () => {
    const otpString = otp.join("");
    if (otpString.length !== 6) return;
    setLoading(true);
    try {
      const res = await api.verifyOtp(phone, otpString);
      setUserId(res.user_id);
      localStorage.setItem("astra_user_id", res.user_id);
      localStorage.setItem("astra_phone", phone);
      toast.success("Phone verified!");
      setStage("kyc");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Verification failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleResendOtp = async () => {
    setLoading(true);
    try {
      const res = await api.sendOtp(phone);
      if (res.dev_otp) setDevOtp(res.dev_otp);
      setOtp(["", "", "", "", "", ""]);
      toast.success("New OTP sent!");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to resend";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleKycSubmit = async () => {
    if (!firstName.trim() || !lastName.trim() || !pan.trim()) return;
    setLoading(true);
    try {
      const res = await api.submitKyc({
        user_id: userId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim() || undefined,
        pan: pan.trim().toUpperCase(),
      });
      setPanType(res.pan_type);
      toast.success(`KYC verified! PAN type: ${res.pan_type}`);
      setStage("scanning");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "KYC submission failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (stage !== "scanning") return;

    setScanApiDone(false);
    setScanAnimDone(false);
    setStepIdx(0);

    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i < scanSteps.length) {
        setStepIdx(i);
      } else {
        clearInterval(interval);
        setScanAnimDone(true);
      }
    }, 1200);

    api.startScan(userId).then(() => {
      setScanApiDone(true);
    }).catch(() => {
      setScanApiDone(true);
    });

    return () => clearInterval(interval);
  }, [stage, userId]);

  useEffect(() => {
    if (scanApiDone && scanAnimDone) {
      setTimeout(() => onComplete(userId), 600);
    }
  }, [scanApiDone, scanAnimDone, userId, onComplete]);

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

            <button
              onClick={nextSlide}
              className="w-full rounded-2xl border border-primary/40 px-6 py-4 font-display font-semibold text-primary text-sm tracking-wide transition-all hover:bg-primary/10 active:scale-[0.98]"
            >
              {slideIdx < slides.length - 1 ? "Next" : "Become a Member"}
            </button>
          </motion.div>
        )}

        {stage === "mobile" && (
          <motion.div
            key="mobile"
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

            <button
              onClick={handleAgree}
              disabled={phone.length < 10 || !agreed || loading}
              className="w-full rounded-2xl bg-primary px-6 py-4 font-display font-semibold text-primary-foreground text-sm transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? "Sending OTP..." : "Agree & Continue"}
            </button>
          </motion.div>
        )}

        {stage === "otp_verify" && (
          <motion.div
            key="otp_verify"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            className="flex w-full max-w-sm flex-col"
          >
            <button
              onClick={() => setStage("mobile")}
              className="flex items-center gap-1 text-muted-foreground text-sm mb-6 hover:text-foreground transition-colors"
            >
              <ArrowLeft size={16} />
              Back
            </button>

            <AstraLogo size={40} />
            <h1 className="font-display text-2xl font-bold text-foreground mt-6 mb-2">
              Enter verification code
            </h1>
            <p className="text-sm text-muted-foreground mb-8">
              We sent a 6-digit code to +91 {phone}
            </p>

            <div className="flex gap-3 mb-6 justify-center">
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => { otpRefs.current[i] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOtpChange(i, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(i, e)}
                  className="w-12 h-14 rounded-xl border border-border bg-card text-center text-lg font-bold text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-all"
                />
              ))}
            </div>

            {devOtp && (
              <button
                onClick={handleAutoFill}
                className="text-xs text-primary/70 mb-4 hover:text-primary transition-colors"
              >
                🔑 Dev: Auto-fill OTP
              </button>
            )}

            <button
              onClick={handleVerifyOtp}
              disabled={otp.join("").length !== 6 || loading}
              className="w-full rounded-2xl bg-primary px-6 py-4 font-display font-semibold text-primary-foreground text-sm transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2 mb-4"
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? "Verifying..." : "Verify OTP"}
            </button>

            <button
              onClick={handleResendOtp}
              disabled={loading}
              className="text-sm text-muted-foreground hover:text-primary transition-colors"
            >
              Didn't receive code? <span className="text-primary font-medium">Resend</span>
            </button>
          </motion.div>
        )}

        {stage === "kyc" && (
          <motion.div
            key="kyc"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            className="flex w-full max-w-sm flex-col"
          >
            <AstraLogo size={40} />
            <h1 className="font-display text-2xl font-bold text-foreground mt-6 mb-2">
              Complete your profile
            </h1>
            <p className="text-sm text-muted-foreground mb-8">
              We need a few details to set up your account.
            </p>

            <div className="space-y-4 mb-8">
              <div className="rounded-2xl border border-border bg-card px-4 py-3.5 focus-within:border-primary transition-colors">
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="Enter first name"
                  className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/40 outline-none text-sm mt-1"
                />
              </div>

              <div className="rounded-2xl border border-border bg-card px-4 py-3.5 focus-within:border-primary transition-colors">
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Enter last name"
                  className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/40 outline-none text-sm mt-1"
                />
              </div>

              <div className="rounded-2xl border border-border bg-card px-4 py-3.5 focus-within:border-primary transition-colors">
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">Email (Optional)</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter email address"
                  className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/40 outline-none text-sm mt-1"
                />
              </div>

              <div className="rounded-2xl border border-border bg-card px-4 py-3.5 focus-within:border-primary transition-colors">
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider font-medium">PAN Number</label>
                <input
                  type="text"
                  maxLength={10}
                  value={pan}
                  onChange={(e) => setPan(e.target.value.toUpperCase())}
                  placeholder="ABCDE1234F"
                  className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/40 outline-none text-sm mt-1 tracking-wider"
                />
              </div>
            </div>

            {panType && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 mb-4 px-4 py-3 rounded-xl bg-primary/10 border border-primary/20"
              >
                <CheckCircle2 size={16} className="text-primary" />
                <span className="text-xs text-primary font-medium">
                  Verified PAN • {panType} Account Detected
                </span>
              </motion.div>
            )}

            <button
              onClick={handleKycSubmit}
              disabled={!firstName.trim() || !lastName.trim() || !pan.trim() || loading}
              className="w-full rounded-2xl bg-primary px-6 py-4 font-display font-semibold text-primary-foreground text-sm transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? "Verifying KYC..." : "Continue"}
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
