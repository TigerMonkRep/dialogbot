"use client";

import NextLink from "next/link";
import type { ComponentProps } from "react";
import { localizeHref } from "./config";
import { useLocale } from "./client";

/** Drop-in for next/link: marketing-page hrefs get the current language prefix ("/priser" → "/de/priser"). */
export default function Link({ href, ...rest }: ComponentProps<typeof NextLink>) {
  const locale = useLocale();
  const h = typeof href === "string" ? localizeHref(locale, href) : href;
  return <NextLink href={h} {...rest} />;
}
