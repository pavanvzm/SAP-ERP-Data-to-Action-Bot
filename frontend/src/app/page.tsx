'use client';

import { useState, useEffect, useRef } from 'react';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  intent?: {
    action: string;
    confidence: number;
    requires_approval: boolean;
  };
}

interface ApprovalRequest {
  id: number;
  action: string;
  details: string;
  requested_by: string;
  timestamp: string;
}

interface ChatResponse {
  conversation_id: string;
  message: string;
  intent?: {
    action: string;
    confidence: number;
    requires_approval: boolean;
    is_safe: boolean;
  };
  status: string;
  data?: any;
  pending_approval_id?: number;
  requires_approval: boolean;
  approval_details?: any;
  error?: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [showApprovals, setShowApprovals] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    fetchApprovals();
    const interval = setInterval(fetchApprovals, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchApprovals = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/approvals/pending');
      const data = await res.json();
      setApprovals(data.approvals || []);
    } catch (error) {
      console.error('Failed to fetch approvals:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input }),
      });

      const data: ChatResponse = await res.json();

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.message || 'Operation completed.',
        timestamp: new Date(),
        intent: data.intent,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (data.requires_approval) {
        fetchApprovals();
        setShowApprovals(true);
      }
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Failed to process request. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprove = async (approvalId: number, approve: boolean) => {
    try {
      await fetch('http://localhost:8000/api/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approval_id: approvalId,
          decision: approve ? 'approve' : 'deny',
          authorized_by: 'admin_user',
        }),
      });
      fetchApprovals();
    } catch (error) {
      console.error('Failed to process approval:', error);
    }
  };

  return (
    <main className="flex h-screen bg-gray-50">
      {/* Left Panel - Chat */}
      <div className="flex-1 flex flex-col border-r border-gray-200">
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-900">ERP Data-to-Action Bot</h1>
              <p className="text-sm text-gray-500">Natural language interface for SAP/ERP operations</p>
            </div>
            <div className="flex items-center gap-4">
              <span className="px-3 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-full">
                ● Online
              </span>
              <button
                onClick={() => setShowApprovals(!showApprovals)}
                className="relative px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
              >
                Approvals
                {approvals.length > 0 && (
                  <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                    {approvals.length}
                  </span>
                )}
              </button>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <div className="text-center py-12">
              <div className="w-16 h-16 mx-auto mb-4 bg-blue-100 rounded-full flex items-center justify-center">
                <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <h2 className="text-lg font-medium text-gray-900 mb-2">Welcome to ERP Bot</h2>
              <p className="text-gray-500 max-w-md mx-auto">
                Ask questions about customers, invoices, or request changes that require approval.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {['Show all customers', 'List pending invoices', 'Dashboard summary'].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setInput(suggestion)}
                    className="px-3 py-1 text-sm bg-white border border-gray-200 rounded-full hover:bg-gray-50 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[70%] rounded-lg px-4 py-3 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : message.content.includes('approval')
                    ? 'bg-amber-50 border border-amber-200'
                    : 'bg-white border border-gray-200'
                }`}
              >
                <p className="text-sm">{message.content}</p>
                {message.intent && (
                  <div className={`mt-2 pt-2 border-t text-xs ${
                    message.role === 'user' ? 'border-blue-500 text-blue-100' : 'border-gray-200 text-gray-500'
                  }`}>
                    <span className="font-medium">Action:</span> {message.intent.action}
                    <span className="ml-2">Confidence: {(message.intent.confidence * 100).toFixed(0)}%</span>
                    {message.intent.requires_approval && (
                      <span className="ml-2 px-2 py-0.5 bg-amber-100 text-amber-700 rounded">Requires Approval</span>
                    )}
                  </div>
                )}
                <p className={`text-xs mt-1 ${
                  message.role === 'user' ? 'text-blue-200' : 'text-gray-400'
                }`}>
                  {message.timestamp.toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="p-4 bg-white border-t border-gray-200">
          <div className="flex gap-3">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about customers, invoices, or request changes..."
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? 'Sending...' : 'Send'}
            </button>
          </div>
        </form>
      </div>

      {/* Right Panel - Approval Dashboard */}
      <div className={`${showApprovals ? 'w-96' : 'w-0'} transition-all duration-300 overflow-hidden bg-white border-l border-gray-200`}>
        <div className="w-96 p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">Pending Approvals</h2>
          {approvals.length === 0 ? (
            <div className="text-center py-8">
              <div className="w-12 h-12 mx-auto mb-3 bg-gray-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-gray-500">No pending approvals</p>
            </div>
          ) : (
            <div className="space-y-4">
              {approvals.map((approval) => (
                <div key={approval.id} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <div className="flex items-start justify-between mb-2">
                    <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                      {approval.action}
                    </span>
                    <span className="text-xs text-gray-500">
                      #{approval.id}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-3">{approval.details}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleApprove(approval.id, true)}
                      className="flex-1 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700 transition-colors"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleApprove(approval.id, false)}
                      className="flex-1 px-3 py-2 bg-red-600 text-white text-sm font-medium rounded hover:bg-red-700 transition-colors"
                    >
                      Deny
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
