import { Controller, Get } from '@nestjs/common';
import { Public } from './auth/public.decorator';

@Controller()
export class AppController {
  @Public()
  @Get('health')
  health(): { status: string; service: string } {
    return { status: 'ok', service: 'api-gateway' };
  }
}
