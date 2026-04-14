import { useState } from "react";
import { motion } from "framer-motion";
import { User, CreditCard, Building2, Shield, LogOut, ChevronRight, Fingerprint, Bell, Moon, History, MapPin, HelpCircle, Info } from "lucide-react";

interface Props {
  onLogout: () => void;
}

const menuItems = [
  { icon: History, label: "Transaction History", desc: "Find all your transactions here" },
  { icon: Shield, label: "Manage your Astra protect", desc: "Find all your transactions here" },
  { icon: User, label: "Manage Account", desc: "Login details and communication preferences" },
  { icon: CreditCard, label: "Payment Settings", desc: "Manage your payment methods" },
  { icon: MapPin, label: "Manage addresses", desc: "All your addresses" },
  { icon: HelpCircle, label: "Support", desc: "24 × 7 helpline available" },
  { icon: Info, label: "About", desc: "" },
];

const ProfileView = ({ onLogout }: Props) => (
  <div className="min-h-screen pb-24 pt-6 px-4 max-w-lg mx-auto">
    {/* Avatar */}
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center mb-8"
    >
      <div className="h-20 w-20 rounded-full bg-card border-2 border-primary flex items-center justify-center text-2xl font-display font-bold text-foreground mb-3">
        PK
      </div>
      <h1 className="font-display text-xl font-bold text-foreground">Pramod Kumar</h1>
      <p className="text-sm text-muted-foreground">+91 98765 43210</p>
      <p className="text-xs text-muted-foreground mt-1">Joined DEC 2024</p>
    </motion.div>

    {/* Menu Items */}
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="rounded-3xl bg-card border border-border/30 overflow-hidden divide-y divide-border/20 mb-6"
    >
      {menuItems.map((item, i) => (
        <motion.button
          key={i}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.15 + i * 0.04 }}
          className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-muted/30 transition-colors"
        >
          <item.icon size={18} className="text-primary shrink-0" strokeWidth={1.5} />
          <div className="flex-1 min-w-0">
            <p className="font-display text-sm font-semibold text-foreground">{item.label}</p>
            {item.desc && <p className="text-[10px] text-muted-foreground mt-0.5">{item.desc}</p>}
          </div>
          <ChevronRight size={14} className="text-muted-foreground shrink-0" />
        </motion.button>
      ))}
    </motion.div>

    {/* Logout */}
    <motion.button
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.5 }}
      onClick={onLogout}
      className="w-full flex items-center justify-center gap-2 rounded-2xl border border-danger/20 bg-danger/5 px-4 py-3.5 text-sm text-danger font-medium transition-colors hover:bg-danger/10"
    >
      <LogOut size={16} />
      Log Out
    </motion.button>
  </div>
);

export default ProfileView;
