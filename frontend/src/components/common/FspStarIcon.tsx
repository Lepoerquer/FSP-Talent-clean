import React from 'react';
import fspLogo from '../../assets/fsp-logo.svg';

export interface FspStarIconProps {
  size?: number | string;
  stroke?: number;
  className?: string;
  style?: React.CSSProperties;
  title?: string;
}

/**
 * Официальная эмблема Федерации спортивного программирования (созвездие / звезда).
 * Импортируется как хэшированный ассет Vite, что гарантирует мгновенное обновление
 * и сброс любого кэша браузера.
 */
export const FspStarIcon: React.FC<FspStarIconProps> = ({
  size = 18,
  stroke: _stroke,
  className,
  style,
  title = 'ФСП',
}) => {
  return (
    <img
      src={fspLogo}
      alt={title}
      title={title}
      width={size}
      height={size}
      className={className}
      style={{
        display: 'inline-block',
        verticalAlign: 'middle',
        flexShrink: 0,
        ...style,
      }}
    />
  );
};
