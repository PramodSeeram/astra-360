import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Camera, ArrowLeft } from "lucide-react";

interface Message {
  id: number;
  role: "user" | "ai";
  text: string;
  agent?: string;
}

interface Props {
  initialAgent?: string;
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
    ai: "All accounts show normal activity. However, I noticed a login attempt from an unrecognized device in Mumbai at 2:14 AM. I've already added it to your watchlist. Would you like to enable two-factor authentication for added security?",
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

const ChatView = ({ initialAgent, onBack }: Props) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);
  const initDone = useRef(false);

  useEffect(() => {
    if (initDone.current) return;
    initDone.current = true;

    if (initialAgent && agentInitialMessages[initialAgent]) {
      const init = agentInitialMessages[initialAgent];
      const userMsg: Message = { id: ++idRef.current, role: "user", text: init.user };
      setMessages([userMsg]);
      setTyping(true);
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { id: ++idRef.current, role: "ai", text: init.ai, agent: init.agent },
        ]);
        setTyping(false);
      }, 1200);
    }
  }, [initialAgent]);

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
    const response =
      text.toLowerCase() === "scamtest"
        ? mockResponses.scamtest
        : mockResponses.default;

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: ++idRef.current, role: "ai", text: response, agent },
      ]);
      setTyping(false);
    }, 1000 + Math.random() * 800);
  };

  const getAgent = (agentId?: string) => agentMap[agentId || "default"] || agentMap.default;

  return (
    <div className="flex h-screen flex-col max-w-lg mx-auto">
      {/* Header */}
      <div className="glass border-b border-border/30 px-4 py-3 flex items-center gap-3">
        <button onClick={onBack} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2 className="font-display text-sm font-semibold text-foreground">Astra 360 Chat</h2>
          <p className="text-[10px] text-primary">Multi-Agent Active</p>
        </div>
      </div>

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
                transition={{ duration: 0.25 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "gradient-teal text-primary-foreground rounded-br-md"
                      : "glass rounded-bl-md"
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
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex justify-start"
          >
            <div className="glass rounded-2xl rounded-bl-md px-4 py-3 flex items-center gap-1">
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
      <div className="border-t border-border/30 p-3 pb-20 sm:pb-3">
        <div className="glass rounded-xl flex items-center gap-2 px-3 py-2">
          <button className="text-muted-foreground hover:text-foreground transition-colors shrink-0">
            <Camera size={18} />
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask Astra anything..."
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="shrink-0 flex h-8 w-8 items-center justify-center rounded-lg gradient-teal text-primary-foreground transition-all disabled:opacity-30 hover:opacity-90 active:scale-90"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
