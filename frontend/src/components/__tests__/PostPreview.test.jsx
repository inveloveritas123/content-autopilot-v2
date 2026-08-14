/**
 * PostPreview unit tests
 *
 * NOTE: This project has no test runner configured (no vitest/jest in package.json).
 * To run these tests, install vitest + @testing-library/react:
 *
 *   npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
 *
 * Then add to package.json "scripts": { "test": "vitest" }
 * and add to vite.config.js: test: { environment: 'jsdom' }
 */

import { render, screen, fireEvent } from '@testing-library/react'
import PostPreview from '../PostPreview'

describe('PostPreview', () => {
  const shortText = 'Kurzer Post ohne Hashtag.'
  const longTextMobile = 'A'.repeat(300) // > 150 (mobile cutoff)
  const mediumText = 'X'.repeat(180) // > 150 (mobile) but < 210 (desktop)

  test('renders three device tabs', () => {
    render(<PostPreview text={shortText} />)
    // getAllByText weil "Mobile" auch im Hint-Text unten vorkommt
    expect(screen.getAllByText(/Desktop/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Tablet/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Mobile/).length).toBeGreaterThan(0)
  })

  test('truncates long text with Mehr anzeigen button on mobile', () => {
    render(<PostPreview text={longTextMobile} defaultDevice="mobile" />)
    expect(screen.getByText('Mehr anzeigen')).toBeTruthy()
  })

  test('expands text on Mehr anzeigen click', () => {
    render(<PostPreview text={longTextMobile} defaultDevice="mobile" />)
    fireEvent.click(screen.getByText('Mehr anzeigen'))
    expect(screen.getByText('Weniger anzeigen')).toBeTruthy()
  })

  test('collapses text on Weniger anzeigen click', () => {
    render(<PostPreview text={longTextMobile} defaultDevice="mobile" />)
    fireEvent.click(screen.getByText('Mehr anzeigen'))
    fireEvent.click(screen.getByText('Weniger anzeigen'))
    expect(screen.getByText('Mehr anzeigen')).toBeTruthy()
  })

  test('desktop has larger cutoff than mobile — no truncation at 180 chars on desktop', () => {
    render(<PostPreview text={mediumText} defaultDevice="desktop" />)
    // At 180 chars, desktop cutoff is 210 — should NOT truncate
    expect(screen.queryByText('Mehr anzeigen')).toBeNull()
  })

  test('mobile truncates at 180 chars when switching to mobile tab', () => {
    render(<PostPreview text={mediumText} defaultDevice="mobile" />)
    // Mobile cutoff is 150, 180 chars > 150 — must truncate
    expect(screen.getByText('Mehr anzeigen')).toBeTruthy()
  })

  test('does not use dangerouslySetInnerHTML — XSS input renders as text', () => {
    const xssText = '<script>alert(1)</script>'
    render(<PostPreview text={xssText} />)
    // Component must render without throwing; script must NOT become a DOM script element
    // React text nodes escape HTML automatically — no dangerouslySetInnerHTML used
    expect(screen.getByText(/Desktop/)).toBeTruthy()
    // The raw text should appear as escaped characters, not as an executed script
    expect(document.querySelectorAll('script').length).toBe(0)
  })

  test('shows carousel badge and first slide title when carouselSlides provided', () => {
    const slides = [{ type: 'cover', title: 'Test Carousel', body: 'Test Body' }]
    render(<PostPreview text="Post mit Carousel" carouselSlides={slides} />)
    expect(screen.getByText(/Carousel \(1 Slides\)/)).toBeTruthy()
    expect(screen.getByText('Test Carousel')).toBeTruthy()
  })

  test('carousel not shown when carouselSlides is null', () => {
    render(<PostPreview text="Normaler Post" carouselSlides={null} />)
    expect(screen.queryByText(/Carousel/)).toBeNull()
  })

  test('renders hashtags with primary color class', () => {
    render(<PostPreview text="Post mit #LinkedIn und #Content" />)
    const hashtag = screen.getByText('#LinkedIn')
    expect(hashtag.className).toContain('text-primary-600')
  })

  test('renders mentions with primary color class', () => {
    render(<PostPreview text="Danke @MaxMustermann fuer den Tipp" />)
    const mention = screen.getByText('@MaxMustermann')
    expect(mention.className).toContain('text-primary-600')
  })

  test('switching device tab resets expansion state for new device', () => {
    render(<PostPreview text={longTextMobile} defaultDevice="mobile" />)
    // Expand on mobile
    fireEvent.click(screen.getByText('Mehr anzeigen'))
    expect(screen.getByText('Weniger anzeigen')).toBeTruthy()
    // Switch to Desktop tab — desktop has its own LinkedInPost instance with own state
    // Desktop-Tab ist der erste mit /Desktop/ — Hint-Text kommt später
    fireEvent.click(screen.getAllByText(/Desktop/)[0])
    // After switching, desktop starts collapsed (180 chars > 210 cutoff? no — 300 > 210, so truncated)
    expect(screen.getByText('Mehr anzeigen')).toBeTruthy()
  })

  test('mobile action bar hides button labels', () => {
    render(<PostPreview text={shortText} defaultDevice="mobile" />)
    // On mobile, text labels inside action buttons are hidden (device !== 'mobile' condition)
    expect(screen.queryByText('Gefällt mir')).toBeNull()
    expect(screen.queryByText('Kommentieren')).toBeNull()
  })

  test('desktop action bar shows button labels', () => {
    render(<PostPreview text={shortText} defaultDevice="desktop" />)
    expect(screen.getByText('Gefällt mir')).toBeTruthy()
    expect(screen.getByText('Kommentieren')).toBeTruthy()
  })

  test('authorName initial shown in avatar', () => {
    render(<PostPreview text={shortText} authorName="Klaus Meister" />)
    // Avatar shows first letter
    expect(screen.getByText('K')).toBeTruthy()
    expect(screen.getByText('Klaus Meister')).toBeTruthy()
  })

  test('mobile tap targets are >= 44px (minHeight/minWidth on buttons)', () => {
    const { container } = render(<PostPreview text={shortText} defaultDevice="mobile" />)
    const actionBtns = container.querySelectorAll('button[style]')
    actionBtns.forEach((btn) => {
      const style = btn.getAttribute('style') || ''
      // Buttons must declare minHeight: 44 or minWidth: 44
      const hasTarget =
        style.includes('44px') ||
        style.includes('min-height: 44') ||
        style.includes('min-width: 44')
      expect(hasTarget).toBe(true)
    })
  })
})
