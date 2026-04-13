/**
 * WhatsApp client wrapper using Baileys.
 * Based on OpenClaw's working implementation.
 */
export interface InboundMessage {
    id: string;
    sender: string;
    pn: string;
    content: string;
    timestamp: number;
    isGroup: boolean;
    wasMentioned?: boolean;
    media?: string[];
}
export interface WhatsAppClientOptions {
    authDir: string;
    onMessage: (msg: InboundMessage) => void;
    onQR: (qr: string) => void;
    onStatus: (status: string) => void;
}
export declare class WhatsAppClient {
    private sock;
    private options;
    private reconnecting;
    constructor(options: WhatsAppClientOptions);
    private normalizeJid;
    private wasMentioned;
    connect(): Promise<void>;
    private downloadMedia;
    private getTextContent;
    sendMessage(to: string, text: string): Promise<void>;
    sendMedia(to: string, filePath: string, mimetype: string, caption?: string, fileName?: string): Promise<void>;
    disconnect(): Promise<void>;
}
