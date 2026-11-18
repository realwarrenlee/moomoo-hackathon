import Image from "next/image"
import Link from "next/link"
import { ArrowLeftIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background p-4 text-center">
      <Image
        src="/moomoo.png"
        alt=""
        width={56}
        height={56}
        className="size-14 rounded-2xl"
      />
      <div className="space-y-2">
        <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          MooTrade · Paper only
        </p>
        <h1 className="text-4xl font-bold tracking-tight tabular-nums">404</h1>
        <p className="text-sm text-muted-foreground">
          This dashboard route does not exist. No order path is hidden here.
        </p>
      </div>
      <Button variant="outline" render={<Link href="/dashboard" />} nativeButton={false}>
        <ArrowLeftIcon />
        Back to Overview
      </Button>
    </div>
  )
}
