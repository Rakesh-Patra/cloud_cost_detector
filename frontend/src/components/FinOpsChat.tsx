import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { 
  Sparkles, 
  Send, 
  Loader2, 
  AlertCircle, 
  Copy, 
  Check, 
  ChevronDown,
  Eraser
} from 'lucide-react';
import { insforge } from '../insforge';

interface ChatMessage {
  role: 'user' | 'model';
  text: string;
}

export default function FinOpsChat() {
  const location = useLocation();
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [history, setHistory] = useState<ChatMessage[]>([
    {
      role: 'model',
      text: "Hi! I'm your FinOps AI Assistant. I have access to your scanned cloud resource inventory and cost recommendations. Ask me anything, or try one of the quick suggestions below!"
    }
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Check if current page is Dashboard (/) or Report (/report)
  const showChat = ['/', '/report'].includes(location.pathname);

  // Automatically scroll to bottom when history changes or chat opens
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [history, isOpen]);

  // Focus input when chat opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  if (!showChat) return null;

  // Retrieve current scan context
  const getContextData = () => {
    // 1. Check if scanResult is available in route state (Report page)
    const scanResult = location.state?.scanResult;
    if (scanResult) {
      return {
        resources: scanResult.resources || [],
        recommendations: scanResult.analysis?.recommendations || []
      };
    }

    // 2. Fallback to localStorage (Dashboard or when navigated without state)
    try {
      const saved = localStorage.getItem('latestScanResult');
      if (saved) {
        const parsed = JSON.parse(saved);
        return {
          resources: parsed.resources || [],
          recommendations: parsed.analysis?.recommendations || []
        };
      }
    } catch (e) {
      console.error('Failed to parse latestScanResult from localStorage:', e);
    }

    return { resources: [], recommendations: [] };
  };

  const handleSend = async (textToSend: string) => {
    const trimmedText = textToSend.trim();
    if (!trimmedText || loading) return;

    setError(null);
    setMessage('');
    
    // Add user message to history
    const updatedHistory = [...history, { role: 'user', text: trimmedText } as ChatMessage];
    setHistory(updatedHistory);
    setLoading(true);

    try {
      const { resources, recommendations } = getContextData();
      const token = (insforge as any).tokenManager.getAccessToken();
      
      const headers = {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      };

      const backendUrl = import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000';
      
      // Exclude the initial welcome message from the backend payload if it's the only model message,
      // but otherwise send full history so Gemini has the proper conversational context.
      const payloadHistory = updatedHistory.slice(0, updatedHistory.length - 1).map(msg => ({
        role: msg.role,
        text: msg.text
      }));

      const response = await fetch(`${backendUrl}/api/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: trimmedText,
          history: payloadHistory,
          resources,
          recommendations
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Chat request failed' }));
        throw new Error(errorData.detail?.message || errorData.detail || 'Failed to get response');
      }

      const data = await response.json();
      
      setHistory(prev => [...prev, { role: 'model', text: data.response || 'No response returned.' }]);
    } catch (err: any) {
      console.error('Error during chat request:', err);
      setError(err.message || 'Could not reach FinOps Assistant. Please check connection.');
      // Keep user's input so they don't lose it on failure
      setMessage(trimmedText);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSend(message);
    }
  };

  const clearChat = () => {
    setHistory([
      {
        role: 'model',
        text: "Hi! I'm your FinOps AI Assistant. I have access to your scanned cloud resource inventory and cost recommendations. Ask me anything, or try one of the quick suggestions below!"
      }
    ]);
    setError(null);
  };

  const quickPrompts = [
    { label: 'How do I upgrade gp2 to gp3?', text: 'How do I upgrade gp2 to gp3?' },
    { label: 'Write a Terraform script for these fixes.', text: 'Write a Terraform script for these fixes.' },
    { label: 'Explain the high-severity issues.', text: 'Explain the high-severity issues.' }
  ];

  return (
    <>
      {/* Floating Toggle Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-40 px-5 py-4 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white rounded-2xl shadow-xl shadow-brandIndigo/25 hover:shadow-brandIndigo/40 hover:scale-105 active:scale-95 transition-all flex items-center gap-2.5 font-semibold text-sm border border-brandIndigo/30 cursor-pointer"
        >
          <Sparkles className="w-4 h-4 animate-pulse text-indigo-200" />
          <span>Ask FinOps AI</span>
        </button>
      )}

      {/* Chat Panel */}
      <div
        className={`fixed bottom-6 right-6 z-50 w-[440px] max-w-[calc(100vw-3rem)] h-[640px] max-h-[calc(100vh-6rem)] bg-zinc-950/80 backdrop-blur-xl border border-zinc-800/80 rounded-3xl shadow-2xl flex flex-col overflow-hidden transition-all duration-300 ease-in-out ${
          isOpen 
            ? 'scale-100 opacity-100 translate-y-0' 
            : 'scale-95 opacity-0 translate-y-4 pointer-events-none'
        }`}
      >
        {/* Header */}
        <div className="px-5 py-4 bg-zinc-900/60 border-b border-zinc-800/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-brandIndigo/15 border border-brandIndigo/30 rounded-xl flex items-center justify-center">
              <Sparkles className="w-4.5 h-4.5 text-brandIndigo" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight">FinOps Assistant</h3>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[10px] font-medium text-zinc-400">Gemini 2.5 Flash</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={clearChat}
              className="p-1.5 hover:bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 rounded-lg transition-all"
              title="Clear Chat History"
            >
              <Eraser className="w-4 h-4" />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 hover:bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 rounded-lg transition-all"
              title="Minimize Panel"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Suggested Quick Buttons */}
        <div className="px-4 py-2.5 bg-zinc-900/20 border-b border-zinc-900 flex flex-wrap gap-1.5">
          {quickPrompts.map((prompt, idx) => (
            <button
              key={idx}
              disabled={loading}
              onClick={() => handleSend(prompt.text)}
              className="px-2.5 py-1.5 bg-zinc-900/50 hover:bg-zinc-800 border border-zinc-800/60 text-zinc-400 hover:text-zinc-200 rounded-lg text-2xs font-medium cursor-pointer transition-all disabled:opacity-50 disabled:pointer-events-none"
            >
              {prompt.label}
            </button>
          ))}
        </div>

        {/* Scrollable Conversation Feed */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {history.map((msg, idx) => {
            const isUser = msg.role === 'user';
            return (
              <div
                key={idx}
                className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] px-4 py-3 rounded-2xl ${
                    isUser
                      ? 'bg-gradient-to-r from-brandIndigo to-brandPurple text-white rounded-br-none shadow-md shadow-brandIndigo/5'
                      : 'bg-zinc-900/65 border border-zinc-800/60 text-zinc-300 rounded-bl-none'
                  }`}
                >
                  {isUser ? (
                    <p className="text-sm leading-relaxed whitespace-pre-wrap font-sans font-medium text-slate-100">{msg.text}</p>
                  ) : (
                    <MarkdownRenderer content={msg.text} />
                  )}
                </div>
              </div>
            );
          })}

          {/* Typing Indicator */}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-zinc-900/65 border border-zinc-800/60 px-4 py-3 rounded-2xl rounded-bl-none flex items-center gap-2">
                <Loader2 className="w-4 h-4 text-brandIndigo animate-spin" />
                <span className="text-xs text-zinc-400 font-medium font-sans">Analyzing request...</span>
              </div>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-950/20 border border-red-900/30 rounded-xl flex items-start gap-2.5 text-xs text-red-400">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">Connection Error:</span> {error}
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 bg-zinc-900/40 border-t border-zinc-800/80 flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyPress}
            disabled={loading}
            placeholder={loading ? "Waiting for response..." : "Ask about your Cloud Cost savings..."}
            className="flex-1 px-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-brandIndigo focus:ring-1 focus:ring-brandIndigo transition-all disabled:opacity-50"
          />
          <button
            onClick={() => handleSend(message)}
            disabled={!message.trim() || loading}
            className="p-3 bg-gradient-to-r from-brandIndigo to-brandPurple hover:from-brandIndigo/90 hover:to-brandPurple/90 text-white rounded-xl shadow-md shadow-brandIndigo/10 hover:shadow-brandIndigo/25 active:scale-95 transition-all disabled:opacity-50 disabled:pointer-events-none cursor-pointer flex items-center justify-center shrink-0 border border-brandIndigo/15"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </>
  );
}


/* --- CUSTOM LIGHTWEIGHT MARKDOWN RENDERING SUB-COMPONENTS --- */

interface MarkdownRendererProps {
  content: string;
}

function MarkdownRenderer({ content }: MarkdownRendererProps) {
  // Split by code blocks: ```
  const parts = content.split(/```/g);
  
  return (
    <div className="space-y-3.5 text-sm text-zinc-300 leading-relaxed font-sans break-words select-text">
      {parts.map((part, index) => {
        // Since split alternates, odd indices are code blocks
        if (index % 2 === 1) {
          const lines = part.split('\n');
          const firstLine = lines[0].trim();
          const isLang = ['json', 'terraform', 'tf', 'bash', 'sh', 'yaml', 'yml', 'python', 'py', 'aws'].includes(firstLine.toLowerCase());
          const language = isLang ? firstLine : '';
          const codeLines = isLang ? lines.slice(1) : lines;
          const code = codeLines.join('\n').trim();
          
          return <CodeBlock key={index} code={code} language={language} />;
        } else {
          return <TextContent key={index} text={part} />;
        }
      })}
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="my-3 bg-zinc-950 border border-zinc-800/80 rounded-xl overflow-hidden shadow-inner font-mono text-[11px] text-emerald-400/90">
      <div className="flex items-center justify-between px-3.5 py-2 bg-zinc-900 border-b border-zinc-800/80 text-zinc-500 text-[9px] font-bold uppercase tracking-wider select-none">
        <span>{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-zinc-300 transition-colors cursor-pointer"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3.5 overflow-x-auto whitespace-pre"><code className="block select-text">{code}</code></pre>
    </div>
  );
}

function TextContent({ text }: { text: string }) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    
    // Check for tables
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      elements.push(<TableBlock key={`table-${i}`} lines={tableLines} />);
      continue;
    }
    
    // Check for headings
    if (line.trim().startsWith('#')) {
      const match = line.match(/^(#{1,6})\s+(.*)$/);
      if (match) {
        const level = match[1].length;
        const headingText = match[2];
        const headingClass = level === 1 
          ? "text-base font-bold text-white mt-4 mb-2 flex items-center gap-1.5" 
          : level === 2 
            ? "text-sm font-bold text-white mt-3.5 mb-2 flex items-center gap-1.5" 
            : "text-xs font-bold text-zinc-200 mt-3 mb-1.5";
        elements.push(
          <div key={`h-${i}`} className={headingClass}>
            {parseInlineMarkdown(headingText)}
          </div>
        );
        i++;
        continue;
      }
    }
    
    // Check for unordered list items
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const listItems: string[] = [];
      while (i < lines.length && (lines[i].trim().startsWith('- ') || lines[i].trim().startsWith('* '))) {
        listItems.push(lines[i].replace(/^[-*]\s+/, ''));
        i++;
      }
      elements.push(
        <ul key={`list-${i}`} className="list-disc pl-5 space-y-1 my-2 text-zinc-300">
          {listItems.map((item, idx) => (
            <li key={idx}>{parseInlineMarkdown(item)}</li>
          ))}
        </ul>
      );
      continue;
    }

    // Check for ordered list items
    if (line.trim().match(/^\d+\.\s+/)) {
      const listItems: string[] = [];
      while (i < lines.length && lines[i].trim().match(/^\d+\.\s+/)) {
        listItems.push(lines[i].replace(/^\d+\.\s+/, ''));
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} className="list-decimal pl-5 space-y-1 my-2 text-zinc-300">
          {listItems.map((item, idx) => (
            <li key={idx}>{parseInlineMarkdown(item)}</li>
          ))}
        </ol>
      );
      continue;
    }
    
    // Default paragraph
    if (line.trim() !== '') {
      elements.push(
        <p key={`p-${i}`} className="my-1.5 text-zinc-300 text-sm leading-relaxed">
          {parseInlineMarkdown(line)}
        </p>
      );
    }
    i++;
  }
  
  return <div className="space-y-0.5">{elements}</div>;
}

function TableBlock({ lines }: { lines: string[] }) {
  const parsedRows = lines.map(line => {
    const parts = line.split('|').map(p => p.trim());
    return parts.slice(1, parts.length - 1);
  });
  
  const rows = parsedRows.filter(row => !row.every(cell => cell.match(/^:?-+:?$/)));
  
  if (rows.length === 0) return null;
  
  const headers = rows[0];
  const bodyRows = rows.slice(1);
  
  return (
    <div className="my-3 overflow-x-auto border border-zinc-800/80 rounded-xl">
      <table className="min-w-full divide-y divide-zinc-800/85 text-[11px] leading-normal">
        <thead className="bg-zinc-900/60 font-semibold text-zinc-300">
          <tr>
            {headers.map((header, idx) => (
              <th key={idx} className="px-3.5 py-2.5 text-left font-bold">{parseInlineMarkdown(header)}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/60 bg-zinc-950/20 text-zinc-400">
          {bodyRows.map((row, rIdx) => (
            <tr key={rIdx} className="hover:bg-zinc-900/5">
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="px-3.5 py-2.5 whitespace-normal">{parseInlineMarkdown(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parseInlineMarkdown(text: string): React.ReactNode[] {
  // Split by inline code: `code`
  const codeParts = text.split(/`/g);
  return codeParts.map((part, index) => {
    if (index % 2 === 1) {
      // Inline code
      return (
        <code key={index} className="px-1.5 py-0.5 bg-zinc-950 border border-zinc-800/60 rounded text-rose-400 font-mono text-[11px] font-medium select-text">
          {part}
        </code>
      );
    } else {
      // Parse bold **text**
      const boldParts = part.split(/\*\*/g);
      return boldParts.map((bPart, bIndex) => {
        if (bIndex % 2 === 1) {
          return <strong key={bIndex} className="font-bold text-white">{bPart}</strong>;
        } else {
          // Parse links [text](url)
          const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
          const elements: React.ReactNode[] = [];
          let lastIndex = 0;
          let match;
          
          while ((match = linkRegex.exec(bPart)) !== null) {
            const matchIndex = match.index;
            if (matchIndex > lastIndex) {
              elements.push(bPart.substring(lastIndex, matchIndex));
            }
            const linkText = match[1];
            const linkUrl = match[2];
            elements.push(
              <a 
                key={matchIndex} 
                href={linkUrl} 
                target="_blank" 
                rel="noopener noreferrer" 
                className="text-brandIndigo hover:underline font-semibold"
              >
                {linkText}
              </a>
            );
            lastIndex = linkRegex.lastIndex;
          }
          
          if (lastIndex < bPart.length) {
            elements.push(bPart.substring(lastIndex));
          }
          
          return <span key={bIndex}>{elements}</span>;
        }
      });
    }
  });
}
