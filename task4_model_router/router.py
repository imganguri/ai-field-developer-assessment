from __future__ import annotations
import asyncio, uuid
from .database import UsageDatabase, RateLimitExceeded
from .providers import ProviderError

def estimate_tokens(prompt: str) -> int:
    """Conservative rough estimate: one token per four UTF-8 bytes, rounded up."""
    return max(1, (len(prompt.encode("utf-8"))+3)//4)

class ModelRouter:
    def __init__(self, db: UsageDatabase, primary, backup, primary_timeout: float=3.0, backup_timeout: float=5.0):
        self.db,self.primary,self.backup=db,primary,backup
        self.primary_timeout,self.backup_timeout=primary_timeout,backup_timeout
    async def complete(self, tenant_hash: str, prompt: str, max_output_tokens: int):
        request_id=str(uuid.uuid4())
        reservation=estimate_tokens(prompt)+max_output_tokens
        try: self.db.reserve(tenant_hash,reservation,request_id)
        except RateLimitExceeded: return 429,{"error":{"code":"RATE_LIMIT_EXCEEDED","message":"Tenant token limit exceeded","request_id":request_id}}
        # One reservation covers both primary and backup. Timeout/failure retains it conservatively.
        primary_timed_out = False
        try:
            try:
                result=await asyncio.wait_for(self.primary.generate(prompt,max_output_tokens),timeout=self.primary_timeout)
            except asyncio.TimeoutError:
                primary_timed_out = True
                try: result=await asyncio.wait_for(self.backup.generate(prompt,max_output_tokens),timeout=self.backup_timeout)
                except Exception: return 503,{"error":{"code":"UPSTREAM_TIMEOUT","message":"Unable to process request","request_id":request_id}}
            except ProviderError as e:
                if e.status != 429: return 502,{"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Unable to process request","request_id":request_id}}
                try: result=await asyncio.wait_for(self.backup.generate(prompt,max_output_tokens),timeout=self.backup_timeout)
                except Exception: return 503,{"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Unable to process request","request_id":request_id}}
            except Exception:
                return 502,{"error":{"code":"UPSTREAM_UNAVAILABLE","message":"Unable to process request","request_id":request_id}}
            usage=result.get("usage", {})
            # A timed-out primary may have consumed its full allocation before
            # cancellation reached the provider; keep the complete reservation.
            if not primary_timed_out and isinstance(usage.get("total_tokens"),int):
                self.db.reconcile(request_id,usage["total_tokens"])
            return 200,{"request_id":request_id,**result}
        except Exception:
            return 500,{"error":{"code":"INTERNAL_ERROR","message":"Unable to process request","request_id":request_id}}
