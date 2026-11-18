"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useTheme } from "next-themes"
import {
  BotIcon,
  ChartNoAxesCombinedIcon,
  GaugeIcon,
  MonitorIcon,
  MoonIcon,
  ScrollTextIcon,
  ShieldCheckIcon,
  SunIcon,
  WalletCardsIcon,
} from "lucide-react"

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"

const pages = [
  { label: "Overview", icon: GaugeIcon, href: "/dashboard" },
  { label: "Portfolio & Orders", icon: WalletCardsIcon, href: "/portfolio" },
  { label: "Risk Centre", icon: ShieldCheckIcon, href: "/risk" },
  { label: "Agent Activity", icon: BotIcon, href: "/agents" },
  { label: "Performance Analytics", icon: ChartNoAxesCombinedIcon, href: "/analytics" },
  { label: "Audit Log", icon: ScrollTextIcon, href: "/audit" },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const router = useRouter()
  const { setTheme } = useTheme()

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((value) => !value)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  const run = useCallback((action: () => void) => {
    setOpen(false)
    action()
  }, [])

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="MooTrade command palette"
      description="Navigate the read-only paper trading dashboard"
    >
      <Command>
        <CommandInput placeholder="Jump to a section..." />
        <CommandList>
          <CommandEmpty>No matching section.</CommandEmpty>
          <CommandGroup heading="MooTrade">
            {pages.map((page) => (
              <CommandItem
                key={page.href}
                onSelect={() => run(() => router.push(page.href))}
              >
                <page.icon className="mr-2 size-4" />
                {page.label}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandSeparator />
          <CommandGroup heading="Theme">
            <CommandItem onSelect={() => run(() => setTheme("light"))}>
              <SunIcon className="mr-2 size-4" />
              Light mode
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTheme("dark"))}>
              <MoonIcon className="mr-2 size-4" />
              Dark mode
            </CommandItem>
            <CommandItem onSelect={() => run(() => setTheme("system"))}>
              <MonitorIcon className="mr-2 size-4" />
              System theme
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
