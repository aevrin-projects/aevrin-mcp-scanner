"use client"
import * as React from "react"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { XIcon } from "lucide-react"

function Dialog({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogOverlay({
  className,
  ...props
}: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      {...props}
    />
  )
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  ...props
}: DialogPrimitive.Popup.Props & {
  showCloseButton?: boolean
}) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        className={cn(
          // The width utilities here are split across two groups on purpose,
          // because `cn` runs tailwind-merge and a caller's `className` has to
          // be able to widen this dialog without silently deleting its
          // viewport guard.
          //
          // This previously read `w-full max-w-[calc(100%-2rem)] sm:max-w-sm`.
          // A caller passing `max-w-2xl` (the install dialog does) collided
          // with `max-w-[calc(100%-2rem)]` -- same utility group -- so
          // tailwind-merge dropped the viewport guard entirely and the dialog
          // rendered edge to edge with no gutter on any screen narrower than
          // 42rem. `sm:max-w-sm` carries a modifier so it was *not* replaced,
          // and being in a later media query it then beat `max-w-2xl` above
          // 640px: the same override was ignored on desktop, pinning the
          // dialog to 24rem. Both measured, not deduced.
          //
          // Expressing the gutter as a *width* leaves the `max-w-*` group free
          // for the caller, and a plain `max-w-sm` default is something an
          // override can actually replace.
          "fixed top-1/2 left-1/2 z-50 grid w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 duration-100 outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          // A grid's implicit column is `auto`, which resolves to max-content:
          // one long unbreakable line (the install dialog's config block puts a
          // whole server URL on one) stretched the column past the dialog and
          // took the footer's negative margins with it. The `overflow-auto` on
          // that block never engaged, because being sized to max-content it had
          // nothing to overflow. `minmax(0,1fr)` lets the column shrink below
          // its content, which is what makes the inner scroller work at all.
          "grid-cols-[minmax(0,1fr)]",
          // A height cap deliberately is *not* set here. It belongs to the
          // dialogs whose content can actually get tall (the install dialog
          // sets its own), because the one edge-anchored caller is a full
          // height nav drawer and `max-h-none` does not reliably beat an
          // arbitrary `max-h-[...]` through tailwind-merge: both survive, and
          // which one wins then depends on stylesheet order rather than on
          // anything the caller wrote.
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            render={
              <Button
                variant="ghost"
                className="absolute top-2 right-2"
                size="icon-sm"
              />
            }
          >
            <XIcon
            />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Popup>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  showCloseButton?: boolean
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "-mx-4 -mb-4 flex flex-col-reverse gap-2 rounded-b-xl border-t bg-muted/50 p-4 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    >
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close render={<Button variant="outline" />}>
          Close
        </DialogPrimitive.Close>
      )}
    </div>
  )
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn(
        "font-heading text-base leading-none font-medium",
        className
      )}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn(
        "text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground",
        className
      )}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
