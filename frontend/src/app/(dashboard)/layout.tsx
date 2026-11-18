import { AppSidebar } from "@/components/app-sidebar"
import { CommandPalette } from "@/components/command-palette"
import { DynamicBreadcrumb } from "@/components/dynamic-breadcrumb"
import { ThemeToggle } from "@/components/theme-toggle"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0 md:overflow-clip">
        <header className="sticky top-0 z-20 flex h-12 shrink-0 items-center border-b bg-background">
          <div className="flex items-center gap-2 px-3 md:px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator
              orientation="vertical"
              className="mr-2 data-vertical:h-4 data-vertical:self-auto"
            />
            <DynamicBreadcrumb />
          </div>
          <div className="ml-auto flex items-center gap-1 pr-3 md:pr-4">
            <ThemeToggle />
          </div>
        </header>
        <CommandPalette />
        <main className="flex flex-1 flex-col">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  )
}
