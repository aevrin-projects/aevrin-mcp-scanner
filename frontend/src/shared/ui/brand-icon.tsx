import amazonWebServices from "thesvg/amazon-web-services";
import anthropic from "thesvg/anthropic";
import azure from "thesvg/azure";
import claude from "thesvg/claude";
import discord from "thesvg/discord";
import docker from "thesvg/docker";
import gemini from "thesvg/google-gemini";
import github from "thesvg/github";
import gitlab from "thesvg/gitlab";
import google from "thesvg/google";
import googleCloud from "thesvg/google-cloud";
import graphql from "thesvg/graphql";
import groq from "thesvg/groq";
import jira from "thesvg/jira";
import kubernetes from "thesvg/kubernetes";
import mongodb from "thesvg/mongodb";
import mysql from "thesvg/mysql";
import notion from "thesvg/notion";
import openai from "thesvg/openai";
import postgresql from "thesvg/postgresql";
import redis from "thesvg/redis";
import slack from "thesvg/slack";
import sqlite from "thesvg/sqlite";
import stripe from "thesvg/stripe";

/**
 * Real company marks, from `thesvg`, instead of hand-copied path data.
 *
 * Every icon here is a build-time constant bundled from the package: the
 * markup never comes from a request, a database or anything a user can
 * influence, which is the only reason `dangerouslySetInnerHTML` is defensible
 * at all. Nothing dynamic may ever be routed through this component.
 *
 * The marks are decorative wherever they are used, because the company is
 * always named in the adjacent text. Each package SVG carries its own
 * `<title>`, which a screen reader would otherwise announce as a duplicate of
 * that name, so the wrapper is `aria-hidden`.
 *
 * Monochrome brands are recoloured to the current text colour rather than
 * drawn in their own hue. OpenAI's brand colour is #000000 and GitHub's is
 * #181717: painted literally, both are invisible against this product's dark
 * theme, in the same way a white mark disappears against the light one. A
 * single-hue mark cannot serve both themes, so it follows the text instead.
 * Brands with a usable mid-tone or multiple colours, Claude and Google, keep
 * their real palette.
 *
 * Keys match the marketplace's own tag vocabulary
 * (`backend/api/aevrin_api/services/marketplace/normalize.py`'s
 * `_TAG_TERMS`) wherever a tag names an actual company, so a listing's own
 * tags can be looked up here directly -- see `ListingLogo` in
 * `entities/marketplace/ui/listing-logo.tsx`. Tags with no real company
 * behind them ("search", "security", "database", "api"...) are deliberately
 * absent; those fall back to a category icon instead.
 */
const BRANDS = {
  anthropic,
  aws: amazonWebServices,
  azure,
  claude,
  discord,
  docker,
  gcp: googleCloud,
  gemini,
  github,
  gitlab,
  google,
  graphql,
  groq,
  jira,
  kubernetes,
  mongodb,
  mysql,
  notion,
  openai,
  postgres: postgresql,
  redis,
  slack,
  sqlite,
  stripe,
} as const;

export type BrandName = keyof typeof BRANDS;
/** Runtime-checkable form of `BrandName`, for callers that only have a
 *  plain string (a listing's tag) and need to know if it names a brand. */
export const BRAND_NAMES = new Set(Object.keys(BRANDS)) as ReadonlySet<BrandName>;

/** sRGB relative luminance, 0 (black) to 1 (white). */
function luminance(hex: string): number {
  const value = hex.replace("#", "");
  if (value.length !== 6) return 0.5;
  const channel = (pair: string) => {
    const srgb = parseInt(pair, 16) / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  return (
    0.2126 * channel(value.slice(0, 2)) +
    0.7152 * channel(value.slice(2, 4)) +
    0.0722 * channel(value.slice(4, 6))
  );
}

/** A mark this dark or this light cannot hold up against both themes. */
function needsCurrentColor(hex: string): boolean {
  const l = luminance(hex);
  return l < 0.06 || l > 0.85;
}

export function BrandIcon({
  name,
  className = "size-4",
  mono,
}: {
  name: BrandName;
  className?: string;
  /**
   * Force the current text colour on, or off. Left undefined, the mark's own
   * brand colour decides, per the rule above.
   */
  mono?: boolean;
}) {
  const brand = BRANDS[name];
  const useCurrentColor = mono ?? needsCurrentColor(brand.hex);
  const markup = useCurrentColor ? (brand.variants?.mono ?? brand.svg) : brand.svg;

  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center ${className} [&>svg]:size-full ${
        useCurrentColor ? "[&_*]:fill-current [&>svg]:fill-current" : ""
      }`}
      dangerouslySetInnerHTML={{ __html: markup }}
    />
  );
}
