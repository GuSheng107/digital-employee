import type { ReactNode } from 'react';
import type { ThemeConfig } from 'antd';
import { ConfigProvider } from 'antd';
import logo from '@/assets/images/avatar/logo.svg';
import styles from './index.module.css';

interface AuthPageShellProps {
  theme: ThemeConfig;
  density?: 'default' | 'compact';
  heroSrc: string;
  brandName?: string;
  brandTitle: string;
  brandSubtitle: string;
  formGreeting: string;
  formTitle: ReactNode;
  formSubtitle: string;
  footer?: ReactNode;
  children: ReactNode;
}

export default function AuthPageShell({
  theme,
  density = 'default',
  heroSrc,
  brandName = 'Digital Employee',
  brandTitle,
  brandSubtitle,
  formGreeting,
  formTitle,
  formSubtitle,
  footer,
  children,
}: AuthPageShellProps): React.ReactElement {
  const containerClass =
    density === 'compact'
      ? `${styles.container} ${styles.compact}`
      : styles.container;

  return (
    <ConfigProvider theme={theme}>
      <div className={containerClass}>
        <section className={styles.brandPanel} aria-label="品牌展示">
          <div className={styles.brandAtmosphere} aria-hidden="true">
            <span className={`${styles.orb} ${styles.orbA}`} />
            <span className={`${styles.orb} ${styles.orbB}`} />
            <span className={`${styles.orb} ${styles.orbC}`} />
            <span className={styles.wave} />
            <span className={`${styles.spark} ${styles.spark1}`} />
            <span className={`${styles.spark} ${styles.spark2}`} />
            <span className={`${styles.spark} ${styles.spark3}`} />
            <span className={`${styles.spark} ${styles.spark4}`} />
            <span className={styles.sheen} />
          </div>

          <header className={styles.brandHeader}>
            <div className={styles.brandMark}>
              <img src={logo} alt="" className={styles.brandMarkImg} />
            </div>
            <span className={styles.brandName}>{brandName}</span>
          </header>

          <div className={styles.brandCopy}>
            <h1 className={styles.brandTitle}>{brandTitle}</h1>
            <p className={styles.brandSubtitle}>{brandSubtitle}</p>
          </div>

          <div className={styles.heroVisual}>
            <div className={styles.heroGlow} />
            <img src={heroSrc} alt="" className={styles.heroArt} />
            <span className={styles.heroShadow} />
          </div>

          <footer className={styles.brandFooter}>
            <span>© {new Date().getFullYear()} {brandName}</span>
          </footer>
        </section>

        <section className={styles.formPanel}>
          <div className={styles.formAtmosphere} aria-hidden="true">
            <span className={`${styles.formOrb} ${styles.formOrbA}`} />
            <span className={`${styles.formOrb} ${styles.formOrbB}`} />
            <span className={`${styles.formOrb} ${styles.formOrbC}`} />
            <span className={styles.formGrid} />
            <span className={styles.formRing} />
            <span className={styles.formSpeck} />
          </div>

          <div className={styles.formStage}>
            <p className={styles.formGreeting}>{formGreeting}</p>
            <h2 className={styles.formTitle}>{formTitle}</h2>
            <p className={styles.formSubtitle}>{formSubtitle}</p>
            {children}
            {footer}
          </div>
        </section>
      </div>
    </ConfigProvider>
  );
}
