import { useEffect, useState, useCallback } from 'react';
import {
  Image as ImageIcon,
  Search,
  X,
  Pencil,
  AlertCircle,
  Trash2,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../stores/auth';
import { cn } from '../lib/utils';

// ── Types ──────────────────────────────────────────────────────────────────

interface MediaRecord {
  id: string;
  timestamp: string;
  prompt: string;
  reference_image: string | null;
  output_images: string[];
  output_text: string;
  model: string;
  status: string;
  error: string | null;
}

interface MediaResponse {
  records: MediaRecord[];
  total: number;
  page: number;
  size: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function imageUrl(path: string): string {
  const filename = path.split('/').pop() || path;
  return `/api/media/images/${filename}`;
}

// ── Grid Card ─────────────────────────────────────────────────────────────

function GridCard({
  record,
  onSelect,
  onDelete,
  deleting,
}: {
  record: MediaRecord;
  onSelect: (r: MediaRecord) => void;
  onDelete?: (r: MediaRecord, e: React.MouseEvent) => void;
  deleting: string | null;
}) {
  const [loaded, setLoaded] = useState(false);
  const hasImage = record.output_images.length > 0;

  return (
    <div
      onClick={() => onSelect(record)}
      className="group cursor-pointer bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl overflow-hidden hover:border-[var(--accent)] transition-all duration-200 relative"
    >
      {hasImage ? (
        <div className={cn('relative aspect-[4/3] overflow-hidden', !loaded && 'bg-[var(--bg-tertiary)] animate-pulse')}>
          <img
            src={imageUrl(record.output_images[0])}
            alt={record.prompt}
            className={cn(
              'w-full h-full object-cover group-hover:scale-105 transition-transform duration-300',
              !loaded && 'opacity-0',
            )}
            loading="lazy"
            onLoad={() => setLoaded(true)}
          />
        </div>
      ) : (
        <div className="aspect-[4/3] flex items-center justify-center bg-[var(--bg-tertiary)]">
          <AlertCircle className="w-8 h-8 text-[var(--danger)] opacity-50" />
        </div>
      )}
      {onDelete && (
        <button
          onClick={e => onDelete(record, e)}
          disabled={deleting === record.id}
          className="absolute top-2 left-2 z-10 p-1.5 rounded-lg bg-black/60 text-white opacity-0 group-hover:opacity-100 hover:bg-[var(--danger)] transition-all"
          title="删除"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
      {record.reference_image && (
        <div className="absolute top-2 right-2 bg-[var(--accent)] text-white rounded-full p-1 z-10" title="编辑模式">
          <Pencil className="w-3 h-3" />
        </div>
      )}
      {record.status === 'error' && (
        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
          <span className="text-xs text-[var(--danger)] font-medium px-2 py-1 bg-black/60 rounded">失败</span>
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-3 py-2 z-10">
        <p className="text-[10px] text-white/80">{new Date(record.timestamp).toLocaleString()}</p>
      </div>
      <div className="absolute bottom-0 left-0 right-0 bg-black/75 backdrop-blur-sm px-3 py-2.5 z-20 translate-y-full group-hover:translate-y-0 transition-transform duration-300">
        <p className="text-xs text-white line-clamp-3 leading-relaxed">{record.prompt}</p>
        <p className="text-[10px] text-white/60 mt-1">{new Date(record.timestamp).toLocaleString()}</p>
      </div>
    </div>
  );
}

// ── Media Page ─────────────────────────────────────────────────────────────

export default function MediaPage() {
  const [data, setData] = useState<MediaResponse | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [selected, setSelected] = useState<MediaRecord | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [jumpToPage, setJumpToPage] = useState('');
  const { canEdit } = useAuth();

  const loadRecords = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), size: '18' });
    if (search) params.set('search', search);
    const res = await api<MediaResponse>(`/media/records?${params}`);
    setData(res);
  }, [page, search]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(1);
  };
  const clearSearch = () => {
    setSearchInput('');
    setSearch('');
    setPage(1);
  };

  const handleDelete = async (record: MediaRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除这条生图记录吗？\n\n${record.prompt.slice(0, 100)}...`)) return;
    setDeleting(record.id);
    setMessage(null);
    try {
      await api(`/media/records/${record.id}`, { method: 'DELETE' });
      setMessage({ type: 'success', text: '删除成功' });
      loadRecords();
      if (selected?.id === record.id) setSelected(null);
    } catch (err: unknown) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : '删除失败' });
    } finally {
      setDeleting(null);
    }
  };

  const totalPages = data ? Math.ceil(data.total / data.size) : 0;

  const handleJumpToPage = () => {
    const targetPage = parseInt(jumpToPage);
    if (targetPage >= 1 && targetPage <= totalPages) {
      setPage(targetPage);
      setJumpToPage('');
    }
  };

  const renderPageNumbers = () => {
    if (totalPages <= 1) return null;

    const pages: (number | string)[] = [];
    const showEllipsis = totalPages > 5;

    if (showEllipsis) {
      let start = Math.max(1, page - 2);
      let end = Math.min(totalPages, page + 2);

      if (end - start < 4) {
        if (start === 1) {
          end = Math.min(totalPages, start + 4);
        } else if (end === totalPages) {
          start = Math.max(1, end - 4);
        }
      }

      if (start > 1) {
        pages.push(1);
        if (start > 2) pages.push('ellipsis-start');
      }

      for (let i = start; i <= end; i++) {
        pages.push(i);
      }

      if (end < totalPages) {
        if (end < totalPages - 1) pages.push('ellipsis-end');
        pages.push(totalPages);
      }
    } else {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    }

    return pages.map(pageNum => {
      if (typeof pageNum === 'string') {
        return (
          <span key={pageNum} className="px-2 text-[var(--text-secondary)]">
            ...
          </span>
        );
      }

      return (
        <button
          key={pageNum}
          onClick={() => setPage(pageNum)}
          className={cn(
            'w-8 h-8 rounded-lg text-sm font-medium transition-colors',
            pageNum === page
              ? 'bg-[var(--accent)] text-white'
              : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
          )}
        >
          {pageNum}
        </button>
      );
    });
  };

  return (
    <div className="h-[calc(100vh-3rem)] flex flex-col">
      {/* Page Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ImageIcon className="w-6 h-6 text-[var(--accent)]" />
            生成图片
          </h1>
          <p className="text-[var(--text-secondary)] text-sm mt-1">AI 图片生成记录</p>
        </div>
        <button
          onClick={loadRecords}
          title="刷新"
          className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Search bar */}
      <div className="shrink-0 flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="relative">
            <input
              type="text"
              placeholder="搜索 prompt..."
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              className="pl-9 pr-8 py-1.5 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-sm text-[var(--text-primary)] w-56"
            />
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-secondary)]" />
            {searchInput && (
              <button onClick={clearSearch} title="清除搜索" className="absolute right-2 top-1/2 -translate-y-1/2">
                <X className="w-3.5 h-3.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]" />
              </button>
            )}
          </div>
          <span className="text-sm text-[var(--text-secondary)]">{data?.total ?? 0} 条记录</span>
        </div>
      </div>

      {message && (
        <div
          className={`shrink-0 mb-4 p-3 rounded-lg text-sm ${message.type === 'success' ? 'bg-[var(--success)]/10 text-[var(--success)]' : 'bg-[var(--danger)]/10 text-[var(--danger)]'}`}
        >
          {message.text}
        </div>
      )}

      {/* Image Grid */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {data?.records.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-[var(--text-secondary)]">
            <ImageIcon className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm">{search ? '没有匹配的记录' : '暂无图片生成记录'}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {data?.records.map(record => (
              <GridCard
                key={record.id}
                record={record}
                onSelect={setSelected}
                onDelete={canEdit() ? handleDelete : undefined}
                deleting={deleting}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer: pagination */}
      <div className="shrink-0 border-t border-[var(--border)] pt-3 mt-3">
        {totalPages > 1 && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <p className="text-sm text-[var(--text-secondary)]">
              共 {data?.total} 条记录 · 第 {page} / {totalPages} 页 · 每页 {data?.size || 18} 张
            </p>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setPage(1)}
                disabled={page <= 1}
                title="首页"
                className="p-2 rounded-lg bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                首页
              </button>

              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page <= 1}
                title="上一页"
                className="p-2 rounded-lg bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <div className="flex items-center gap-1">{renderPageNumbers()}</div>

              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page >= totalPages}
                title="下一页"
                className="p-2 rounded-lg bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
                title="末页"
                className="p-2 rounded-lg bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                末页
              </button>

              <div className="flex items-center gap-2 ml-2">
                <span className="text-sm text-[var(--text-secondary)]">跳至</span>
                <input
                  type="number"
                  min="1"
                  max={totalPages}
                  value={jumpToPage}
                  onChange={e => setJumpToPage(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleJumpToPage()}
                  placeholder={String(page)}
                  className="w-16 px-2 py-1 text-sm text-center rounded-lg bg-[var(--bg-secondary)] border border-[var(--border)] text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
                />
                <button
                  onClick={handleJumpToPage}
                  disabled={!jumpToPage || parseInt(jumpToPage) < 1 || parseInt(jumpToPage) > totalPages}
                  className="px-3 py-1 text-sm rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  确定
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selected && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-6"
          onClick={() => setSelected(null)}
        >
          <div
            className="bg-[var(--bg-primary)] border border-[var(--border)] rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            {selected.output_images.length > 0 && (
              <div className="bg-[var(--bg-tertiary)] flex items-center justify-center p-4">
                <img
                  src={imageUrl(selected.output_images[0])}
                  alt={selected.prompt}
                  className="max-h-[50vh] rounded-lg object-contain"
                />
              </div>
            )}
            <div className="p-6 space-y-4">
              <div>
                <label className="text-xs font-medium text-[var(--text-secondary)] uppercase">Prompt</label>
                <p className="mt-1 text-sm text-[var(--text-primary)] leading-relaxed">{selected.prompt}</p>
              </div>
              {selected.reference_image && (
                <div>
                  <label className="text-xs font-medium text-[var(--text-secondary)] uppercase">参考图片</label>
                  <p className="mt-1 text-xs text-[var(--text-secondary)] font-mono break-all">
                    {selected.reference_image}
                  </p>
                </div>
              )}
              {selected.output_text && (
                <div>
                  <label className="text-xs font-medium text-[var(--text-secondary)] uppercase">模型输出文本</label>
                  <p className="mt-1 text-sm text-[var(--text-primary)]">{selected.output_text}</p>
                </div>
              )}
              {selected.error && (
                <div>
                  <label className="text-xs font-medium text-[var(--danger)] uppercase">错误</label>
                  <p className="mt-1 text-sm text-[var(--danger)]">{selected.error}</p>
                </div>
              )}
              <div className="flex items-center gap-6 text-xs text-[var(--text-secondary)]">
                <span>模型: {selected.model}</span>
                <span>
                  状态:{' '}
                  <span className={selected.status === 'success' ? 'text-[var(--success)]' : 'text-[var(--danger)]'}>
                    {selected.status}
                  </span>
                </span>
                <span>{new Date(selected.timestamp).toLocaleString()}</span>
              </div>
              {selected.output_images.length > 1 && (
                <div>
                  <label className="text-xs font-medium text-[var(--text-secondary)] uppercase mb-2 block">
                    所有输出图片 ({selected.output_images.length})
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {selected.output_images.map((img, i) => (
                      <img
                        key={i}
                        src={imageUrl(img)}
                        alt={`Output ${i + 1}`}
                        className="rounded-lg object-cover aspect-square"
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="border-t border-[var(--border)] px-6 py-4 flex justify-end">
              <button
                onClick={() => setSelected(null)}
                className="px-4 py-2 rounded-lg bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] text-sm"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
