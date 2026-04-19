import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  User,
  ChevronRight,
  Fingerprint,
  Shield,
  Lock,
  LogOut,
  Building2,
  CheckCircle2,
  Smartphone,
  KeyRound,
  Loader2,
  Car,
  Bike,
} from "lucide-react";
import { api, ProfileData } from "@/lib/api";

interface Props {
  onLogout: () => void;
}

interface SecuritySetting {
  icon: typeof Shield;
  label: string;
  desc: string;
  hasToggle: boolean;
  defaultOn: boolean;
}

const securitySettings: SecuritySetting[] = [
  {
    icon: Fingerprint,
    label: "Biometric Login",
    desc: "Use fingerprint or face unlock",
    hasToggle: true,
    defaultOn: true,
  },
  {
    icon: Smartphone,
    label: "Two-Factor Authentication",
    desc: "SMS + App verification",
    hasToggle: true,
    defaultOn: true,
  },
  {
    icon: KeyRound,
    label: "Change PIN",
    desc: "Update your 4-digit Astra PIN",
    hasToggle: false,
    defaultOn: false,
  },
  {
    icon: Lock,
    label: "App Lock Timeout",
    desc: "Lock after 2 minutes of inactivity",
    hasToggle: true,
    defaultOn: false,
  },
];

const NeonToggle = ({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) => (
  <button
    onClick={onToggle}
    className={`relative h-7 w-12 rounded-full transition-colors duration-300 ${
      enabled ? "bg-[#CCFF00]" : "bg-white/10"
    }`}
  >
    <motion.div
      className={`absolute top-0.5 h-6 w-6 rounded-full shadow-md ${
        enabled ? "bg-black" : "bg-gray-400"
      }`}
      animate={{ left: enabled ? "calc(100% - 1.625rem)" : "0.125rem" }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
    />
  </button>
);

const ProfileScreen = ({ onLogout }: Props) => {
  const [data, setData] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggles, setToggles] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    securitySettings.forEach((s) => {
      if (s.hasToggle) initial[s.label] = s.defaultOn;
    });
    return initial;
  });

  useEffect(() => {
    const userId = localStorage.getItem("user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getProfile(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[ProfileScreen] API error:", err))
      .finally(() => setLoading(false));
  }, []);

  const handleToggle = (label: string) => {
    setToggles((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

  const name = data?.full_name || "User";
  const initials = data?.initials || "U";
  const phone = data?.phone || "No phone linked";
  const joinedDate = data?.joined_at ? new Date(data.joined_at).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : "Recently";
  const linkedAccounts = data?.linked_accounts || [];
  const hasData = data?.has_data ?? false;

  return (
    <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
      {/* Profile Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col items-center mb-8"
      >
        <div className="relative mb-4">
          <div className="h-22 w-22 rounded-full bg-gradient-to-br from-[#CCFF00]/20 to-transparent border-2 border-[#CCFF00] flex items-center justify-center shadow-[0_0_25px_rgba(204,255,0,0.2)]"
               style={{ height: '5.5rem', width: '5.5rem' }}>
            <span className="font-display text-2xl font-bold text-white">
              {initials}
            </span>
          </div>
          <motion.div
            className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-[#CCFF00] flex items-center justify-center"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.3, type: "spring" }}
          >
            <CheckCircle2 size={14} className="text-black" />
          </motion.div>
        </div>
        <h1 className="font-display text-xl font-bold text-white">
          {name}
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">{phone}</p>
        <p className="text-xs text-gray-500 mt-1">Joined {joinedDate}</p>
      </motion.div>

      {/* Linked Accounts */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-3">
          <Building2 size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Linked Accounts (Account Aggregator)
          </h2>
        </div>

        <div className="space-y-2.5">
          {!hasData || linkedAccounts.length === 0 ? (
            <div className="rounded-2xl bg-[#1E1E1E] border border-dashed border-white/10 p-8 text-center">
              <p className="text-sm text-gray-500">
                {data?.message || "Link your bank accounts via Account Aggregator to see them here."}
              </p>
            </div>
          ) : (
            linkedAccounts.map((acc, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -15 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + i * 0.06 }}
                className="rounded-2xl bg-[#1E1E1E] border border-white/5 px-4 py-3.5 flex items-center gap-3"
              >
                <div
                  className={`h-10 w-10 rounded-xl bg-white flex items-center justify-center shrink-0 overflow-hidden border border-white/10`}
                >
                  {acc.short_name === "KOTAK" ? (
                    <div className="relative h-10 w-10 flex items-center justify-center">
                      {/* Background fallback */}
                      <div className="absolute inset-0 bg-[#005ea8] rounded-xl flex items-center justify-center font-extrabold text-white text-[18px]">
                        K
                      </div>
                      <img 
                        src="https://logos-download.com/wp-content/uploads/2016/06/Kotak_Mahindra_Bank_logo.png" 
                        alt="Kotak" 
                        className="relative z-10 h-full w-full object-contain p-1"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    </div>
                  ) : (
                    <span className="text-black font-display text-[11px] font-extrabold">
                      {acc.short_name}
                    </span>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-display text-sm font-semibold text-white truncate">
                    {acc.bank}
                  </p>
                  <p className="text-xs text-gray-400">
                    {acc.type} • {acc.acc_no}
                  </p>
                </div>
                <span className="shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 rounded-full px-2.5 py-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Linked
                </span>
              </motion.div>
            ))
          )}
        </div>

        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-3 w-full rounded-xl border border-dashed border-white/10 py-3 text-xs text-gray-400 font-medium hover:border-[#CCFF00]/30 hover:text-[#CCFF00] transition-colors"
        >
          + Link Another Account
        </motion.button>
      </motion.div>

      {/* Insurance Section */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-3">
          <Shield size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Insurance Details
          </h2>
        </div>

        <div className="grid grid-cols-1 gap-2.5">
          {[
            { title: "Life Insurance", detail: "Policy ID: LIFE-XXXX", value: "₹10,00,000", Icon: Shield, color: "text-emerald-400" },
            { title: "Mobile Insurance", detail: "Slice Protect", value: "₹20,000", Icon: Smartphone, color: "text-blue-400" },
            { title: "Vehicle Insurance", detail: "Comprehensive", value: "80% + ₹2,000 deductible", Icon: Car, color: "text-amber-400" },
            { title: "Bike Insurance", detail: "Standard", value: "80% + ₹2,000 deductible", Icon: Bike, color: "text-violet-400" },
          ].map((ins, i) => (
            <motion.div
              key={i}
              className="rounded-2xl bg-[#1E1E1E] border border-white/5 px-4 py-3.5 flex items-center gap-3"
              whileHover={{ scale: 1.01 }}
            >
              <div className={`h-10 w-10 rounded-xl bg-white/5 flex items-center justify-center shrink-0`}>
                <ins.Icon size={18} className={ins.color} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-display text-sm font-semibold text-white">
                  {ins.title}
                </p>
                <p className="text-[10px] text-gray-500 uppercase tracking-tight">
                  {ins.detail}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs font-bold text-white">{ins.value}</p>
                <p className="text-[9px] text-[#CCFF00]/60 font-medium">Covered</p>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Security Settings */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-3">
          <Shield size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Security Settings
          </h2>
        </div>

        <div className="rounded-3xl bg-[#1E1E1E] border border-white/5 overflow-hidden divide-y divide-white/5">
          {securitySettings.map((setting, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 + i * 0.05 }}
              className="flex items-center gap-4 px-5 py-4"
            >
              <div className="shrink-0 h-9 w-9 rounded-xl bg-white/5 flex items-center justify-center">
                <setting.icon
                  size={16}
                  className="text-gray-400"
                  strokeWidth={1.5}
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-display text-sm font-semibold text-white">
                  {setting.label}
                </p>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {setting.desc}
                </p>
              </div>
              {setting.hasToggle ? (
                <NeonToggle
                  enabled={toggles[setting.label] ?? false}
                  onToggle={() => handleToggle(setting.label)}
                />
              ) : (
                <ChevronRight size={14} className="text-gray-500 shrink-0" />
              )}
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Logout */}
      <motion.button
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.55 }}
        whileTap={{ scale: 0.97 }}
        onClick={onLogout}
        className="w-full flex items-center justify-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3.5 text-sm text-red-500 font-semibold transition-colors hover:bg-red-500/15"
      >
        <LogOut size={16} />
        Log Out
      </motion.button>
    </div>
  );
};

export default ProfileScreen;
