import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Camera, ArrowLeft, Clock, Plus, X, MessageSquare, Loader2 } from "lucide-react";
import { api, ChatHistoryMessage, ChatThread } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "ai";
  text: string;
  agentUsed?: string;
  agentsUsed?: string[];
}

interface Props {
  initialAgent?: string;
  initialMessage?: string;
  onBack: () => void;
}

function formatAgentLabel(agent?: string): string {
  if (!agent?.trim()) return "";
  const map: Record<string, string> = {
    spending_agent: "Spending",
    budget_agent: "Budget",
    wealth_agent: "Card & Credit",
    teller_agent: "Account",
    scam_agent: "Fraud & Security",
    claims_agent: "Insurance",
    billing_agent: "Bills & Subscriptions",
    default_agent: "General",
  };
  const mapped = map[agent.trim().toLowerCase()];
  if (mapped) return mapped;
  const words = agent.replace(/_/g, " ").trim().split(/\s+/);
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(" ");
}

function formatAgentBadge(agentsUsed?: string[], agentUsed?: string): string {
  const normalized = (agentsUsed || [])
    .map((agent) => formatAgentLabel(agent))
    .filter((label) => label.length > 0);
  if (normalized.length > 0) return `🧠 ${normalized.join(" • ")}`;
  const single = formatAgentLabel(agentUsed);
  return single ? `🧠 ${single}` : "";
}

interface WelcomeData {
  message: string;
  subheading: string;
  suggestions: string[];
}

const ChatView = ({ initialAgent, initialMessage, onBack }: Props) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [agentHint, setAgentHint] = useState(initialAgent);
  const [welcomeData, setWelcomeData] = useState<WelcomeData | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initSent = useRef(false);

  const userName = localStorage.getItem("user_name") || "User";
  const userId = localStorage.getItem("user_id") || "";

  const loadThreads = async (preferredThreadId?: number | null) => {
    if (!userId) return;
    const threadList = await api.getChatThreads(userId);
    setThreads(threadList);

    if (preferredThreadId) {
      setActiveThreadId(preferredThreadId);
      return;
    }

    if (!activeThreadId && threadList.length > 0) {
      setActiveThreadId(threadList[0].id);
    }
  };

  const loadHistory = async (threadId: number) => {
    if (!userId) return;
    setLoadingHistory(true);
    try {
      const history = await api.getChatHistory(userId, threadId);
      setMessages(
        history.map((msg: ChatHistoryMessage) => ({
          id: msg.id,
          role: msg.role === "assistant" ? "ai" : "user",
          text: msg.content,
        })),
      );
    } catch (error) {
      console.error("[ChatView] history error:", error);
      setMessages([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    setAgentHint(initialAgent);
  }, [initialAgent]);

  useEffect(() => {
    if (!userId) return;
    api.getWelcome(userId)
      .then(setWelcomeData)
      .catch(() => {/* welcome is best-effort */});
  }, [userId]);

  useEffect(() => {
    loadThreads().catch((error) => {
      console.error("[ChatView] threads error:", error);
      setLoadingHistory(false);
    });
  }, []);

  useEffect(() => {
    if (activeThreadId === null) {
      setLoadingHistory(false);
      setMessages([]);
      return;
    }
    loadHistory(activeThreadId).catch((error) => {
      console.error("[ChatView] load history error:", error);
      setLoadingHistory(false);
    });
  }, [activeThreadId]);

  useEffect(() => {
    if (!initialMessage || initSent.current || !userId || loadingHistory) {
      return;
    }
    if (activeThreadId !== null) {
      return;
    }

    initSent.current = true;
    setInput(initialMessage);
  }, [initialMessage, userId, loadingHistory, activeThreadId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const handleSend = async (forcedText?: string) => {
    const text = (forcedText ?? input).trim();
    if (!text || !userId) return;

    if (!forcedText) {
      setInput("");
    }

    const optimisticId = Date.now();
    setMessages((prev) => [...prev, { id: optimisticId, role: "user", text }]);
    setTyping(true);

    try {
      const requestAgentHint = activeThreadId === null ? agentHint : undefined;
      const data = await api.chat(userId, text, activeThreadId ?? undefined, requestAgentHint);
      const returnedThreadId = data.data?.thread_id ?? null;
      if (returnedThreadId && returnedThreadId !== activeThreadId) {
        setActiveThreadId(returnedThreadId);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: optimisticId + 1,
          role: "ai",
          text: data.response,
          agentUsed: data.data?.agent_used,
          agentsUsed: data.data?.agents_used,
        },
      ]);

      await loadThreads(returnedThreadId ?? activeThreadId);
    } catch (error) {
      console.error("Chat Error:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: optimisticId + 1,
          role: "ai",
          text: "I’m having trouble reaching the backend right now. Please try again in a moment.",
        },
      ]);
    } finally {
      setTyping(false);
      setAgentHint(undefined);
    }
  };

  useEffect(() => {
    if (input === initialMessage && initialMessage && initSent.current) {
      handleSend(initialMessage).catch((error) => console.error("[ChatView] initial send error:", error));
      setInput("");
    }
  }, [input, initialMessage]);

  const handleNewChat = () => {
    setActiveThreadId(null);
    setMessages([]);
    setHistoryOpen(false);
  };

  return (
    <div className="flex h-screen flex-col max-w-lg mx-auto">
      <div className="bg-card/90 backdrop-blur-xl border-b border-border/20 px-4 py-3 flex items-center gap-3 relative z-10">
        <button onClick={onBack} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2 className="font-display text-sm font-semibold text-foreground">Welcome, {userName}</h2>
          <p className="text-[10px] text-primary">
            {threads.find((thread) => thread.id === activeThreadId)?.title || "New Chat"}
          </p>
        </div>
        <button
          onClick={() => setHistoryOpen(true)}
          className="ml-auto text-muted-foreground hover:text-[#CCFF00] transition-colors rounded-full p-2 bg-white/5 border border-white/5"
        >
          <Clock size={16} />
        </button>
      </div>

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
                  onClick={handleNewChat}
                  className="w-full rounded-xl bg-[#CCFF00] px-4 py-3 flex items-center justify-center gap-2 mb-6 transition-all active:scale-95 text-black"
                >
                  <Plus size={18} />
                  <span className="font-bold text-sm">New Chat</span>
                </button>

                <div className="space-y-1">
                  <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">
                    Recent Threads
                  </p>
                  {threads.length === 0 ? (
                    <p className="text-sm text-gray-500 px-1">No saved conversations yet.</p>
                  ) : (
                    threads.map((thread) => (
                      <button
                        key={thread.id}
                        onClick={() => {
                          setActiveThreadId(thread.id);
                          setHistoryOpen(false);
                        }}
                        className={`w-full text-left p-3 rounded-xl transition-colors group flex gap-3 ${
                          activeThreadId === thread.id ? "bg-white/10" : "hover:bg-white/5"
                        }`}
                      >
                        <MessageSquare size={16} className="text-gray-500 group-hover:text-[#CCFF00] shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <p className="text-sm text-white font-medium line-clamp-1">{thread.title}</p>
                          <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-2">{thread.preview || "No preview yet"}</p>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {loadingHistory ? (
          <div className="h-full flex items-center justify-center">
            <Loader2 size={28} className="text-[#CCFF00] animate-spin" />
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {messages.map((msg) => (
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
                  {msg.role === "ai" && formatAgentBadge(msg.agentsUsed, msg.agentUsed) ? (
                    <div className="mb-2 inline-flex rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-primary">
                      {formatAgentBadge(msg.agentsUsed, msg.agentUsed)}
                    </div>
                  ) : null}
                  <p className="whitespace-pre-wrap break-words">{typeof msg.text === "string" ? msg.text : ""}</p>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        )}

        {!loadingHistory && messages.length === 0 && !typing && (
          <div className="rounded-2xl bg-card border border-border/30 px-4 py-5">
            {welcomeData ? (
              <>
                <p className="text-sm font-semibold text-foreground mb-0.5">{welcomeData.message}</p>
                <p className="text-xs text-muted-foreground mb-3">{welcomeData.subheading}</p>
                <div className="flex flex-col gap-2">
                  {welcomeData.suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSend(s)}
                      className="text-left text-xs rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-primary hover:bg-primary/10 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                Ask about spending, bills, budgeting, fraud, insurance, or credit and this thread will be saved automatically.
              </p>
            )}
          </div>
        )}

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
            onClick={() => handleSend()}
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
