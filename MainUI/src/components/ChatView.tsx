import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Camera, ArrowLeft, Clock, Plus, X, MessageSquare } from "lucide-react";

interface Message {
  id: number;
  role: "user" | "ai";
  text: string;
  agent?: string;
}

interface Props {
  initialAgent?: string;
  initialMessage?: string;
  onBack: () => void;
}

const agentMap: Record<string, { name: string; badge: string }> = {
  wealth: { name: "Wealth Optimizer Agent", badge: "📈" },
  teller: { name: "Virtual Teller Agent", badge: "🤖" },
  scam: { name: "Scam Defender Agent", badge: "🛡️" },
  claims: { name: "Claims Adjuster Agent", badge: "📋" },
  default: { name: "Astra 360 Agent", badge: "⭐" },
};

const agentInitialMessages: Record<string, { user: string; ai: string; agent: string }> = {
  wealth: {
    user: "How can I optimize my portfolio?",
    ai: "I've analyzed your current holdings. Your portfolio is 70% equity and 30% debt. Given your risk profile, I recommend shifting 10% from large-cap to mid-cap funds for better growth potential. Shall I show a detailed breakdown?",
    agent: "wealth",
  },
  teller: {
    user: "What's my account summary?",
    ai: "Here's your summary:\n• **SBI Savings:** ₹45,200\n• **HDFC Savings:** ₹74,800\n• **Total:** ₹1,20,000\n\nYour last 3 transactions were all verified. Would you like to make a transfer?",
    agent: "teller",
  },
  scam: {
    user: "Are my accounts secure?",
    ai: "All accounts show normal activity. However, I noticed a login attempt from an unrecognized device in Mumbai at 2:14 AM. I've already added it to your watchlist. Would you like to enable two-factor authentication?",
    agent: "scam",
  },
  claims: {
    user: "I need to file a claim",
    ai: "I can help you file an insurance claim. To get started, I'll need:\n1. **Policy number**\n2. **Date of incident**\n3. **Brief description**\n\nYou can also upload a photo of any relevant documents using the camera icon below.",
    agent: "claims",
  },
};

const mockResponses: Record<string, string> = {
  scamtest: "🚨 ALERT: I'm detecting suspicious activity right now! Triggering threat analysis...",
  default: "I understand your query. Let me analyze this with our multi-agent system. Based on your financial profile, here are my recommendations...",
};

const mockHistory = [
  { id: 1, title: "Optimize portfolio allocation", date: "Today" },
  { id: 2, title: "How to improve CIBIL score", date: "Yesterday" },
  { id: 3, title: "Check HDFC FD maturity", date: "2 days ago" },
  { id: 4, title: "Suspicious login from Mumbai", date: "Last week" },
];

const ChatView = ({ initialAgent, initialMessage, onBack }: Props) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);
  const initDone = useRef(false);

  useEffect(() => {
    if (initDone.current) return;
    initDone.current = true;
    if (initialMessage) {
      // Pre-filled question from another screen (e.g. credit score "How to Improve")
      const userMsg: Message = { id: ++idRef.current, role: "user", text: initialMessage };
      setMessages([userMsg]);
      setTyping(true);
      const agent = detectAgent(initialMessage);
      setTimeout(() => {
        setMessages((prev) => [...prev, {
          id: ++idRef.current,
          role: "ai",
          text: "Great question! Here are my top recommendations to improve your CIBIL score:\n\n📌 **1. Reduce Credit Utilization** — You're at 24%. Aim for under 20% by paying mid-cycle.\n\n📌 **2. Never Miss a Payment** — Set up auto-pay for all cards and EMIs.\n\n📌 **3. Don't Close Old Cards** — Your oldest card (3.4 yrs) helps your credit age.\n\n📌 **4. Limit Hard Enquiries** — Avoid applying for new credit for 6 months.\n\n📌 **5. Diversify Credit Mix** — A small secured loan can improve your mix score.\n\nWant me to set up auto-pay reminders or create a personalized credit improvement plan?",
          agent: "wealth",
        }]);
        setTyping(false);
      }, 1500);
    } else if (initialAgent && agentInitialMessages[initialAgent]) {
      const init = agentInitialMessages[initialAgent];
      const userMsg: Message = { id: ++idRef.current, role: "user", text: init.user };
      setMessages([userMsg]);
      setTyping(true);
      setTimeout(() => {
        setMessages((prev) => [...prev, { id: ++idRef.current, role: "ai", text: init.ai, agent: init.agent }]);
        setTyping(false);
      }, 1200);
    }
  }, [initialAgent, initialMessage]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const detectAgent = (text: string): string => {
    const lower = text.toLowerCase();
    if (lower.includes("invest") || lower.includes("portfolio") || lower.includes("wealth")) return "wealth";
    if (lower.includes("balance") || lower.includes("transfer") || lower.includes("account")) return "teller";
    if (lower.includes("scam") || lower.includes("fraud") || lower.includes("suspicious")) return "scam";
    if (lower.includes("claim") || lower.includes("insurance") || lower.includes("policy")) return "claims";
    return "default";
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    const userMsg: Message = { id: ++idRef.current, role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setTyping(true);
    const agent = detectAgent(text);
    const response = text.toLowerCase() === "scamtest" ? mockResponses.scamtest : mockResponses.default;
    setTimeout(() => {
      setMessages((prev) => [...prev, { id: ++idRef.current, role: "ai", text: response, agent }]);
      setTyping(false);
    }, 1000 + Math.random() * 800);
  };

  const getAgent = (agentId?: string) => agentMap[agentId || "default"] || agentMap.default;

  return (
    <div className="flex h-screen flex-col max-w-lg mx-auto">
      {/* Header */}
      <div className="bg-card/90 backdrop-blur-xl border-b border-border/20 px-4 py-3 flex items-center gap-3 relative z-10">
        <button onClick={onBack} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2 className="font-display text-sm font-semibold text-foreground">Astra 360 Chat</h2>
          <p className="text-[10px] text-primary">Multi-Agent Active</p>
        </div>
        <button 
          onClick={() => setHistoryOpen(true)}
          className="ml-auto text-muted-foreground hover:text-[#CCFF00] transition-colors rounded-full p-2 bg-white/5 border border-white/5"
        >
          <Clock size={16} />
        </button>
      </div>

      {/* History Slide-over */}
      <AnimatePresence>
        {historyOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setHistoryOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm z-20"
            />
            <motion.div
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              className="absolute right-0 top-0 bottom-0 w-[80%] max-w-[320px] bg-[#1A1A1A] border-l border-white/10 z-30 flex flex-col"
            >
              <div className="p-4 border-b border-white/10 flex items-center justify-between">
                <h3 className="font-display text-base font-bold text-white">Chat History</h3>
                <button onClick={() => setHistoryOpen(false)} className="text-gray-400 hover:text-white">
                  <X size={20} />
                </button>
              </div>
              <div className="p-4">
                <button 
                  onClick={() => {
                    setMessages([]);
                    setHistoryOpen(false);
                  }}
                  className="w-full rounded-xl bg-[#CCFF00] px-4 py-3 flex items-center justify-center gap-2 mb-6 transition-all active:scale-95 text-black"
                >
                  <Plus size={18} />
                  <span className="font-bold text-sm">New Chat</span>
                </button>

                <div className="space-y-1">
                  <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">Recent Threads</p>
                  {mockHistory.map((thread) => (
                    <button
                      key={thread.id}
                      onClick={() => setHistoryOpen(false)}
                      className="w-full text-left p-3 rounded-xl hover:bg-white/5 transition-colors group flex gap-3"
                    >
                      <MessageSquare size={16} className="text-gray-500 group-hover:text-[#CCFF00] shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm text-white font-medium line-clamp-1">{thread.title}</p>
                        <p className="text-[10px] text-gray-500 mt-0.5">{thread.date}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <AnimatePresence initial={false}>
          {messages.map((msg) => {
            const agent = msg.role === "ai" ? getAgent(msg.agent) : null;
            return (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-md"
                      : "bg-card border border-border/30 rounded-bl-md"
                  }`}
                >
                  {agent && (
                    <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold text-primary uppercase tracking-wider">
                      <span>{agent.badge}</span>
                      {agent.name}
                    </div>
                  )}
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>

        {typing && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="bg-card border border-border/30 rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1">
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-primary"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                />
              ))}
            </div>
          </motion.div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border/20 p-3 pb-4">
        <div className="rounded-2xl bg-card border border-border/30 flex items-center gap-2 px-3 py-2 focus-within:border-primary/40 transition-colors">
          <button className="text-muted-foreground hover:text-foreground transition-colors shrink-0">
            <Camera size={18} />
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask Astra anything..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/40 outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="shrink-0 flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-all disabled:opacity-30 hover:opacity-90 active:scale-90"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
