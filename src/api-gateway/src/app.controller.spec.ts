import { Test, TestingModule } from '@nestjs/testing';
import { AppController } from './app.controller';

describe('AppController', () => {
  let controller: AppController;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [AppController],
    }).compile();

    controller = module.get<AppController>(AppController);
  });

  describe('health', () => {
    it('should report ok', () => {
      expect(controller.health()).toEqual({ status: 'ok', service: 'api-gateway' });
    });
  });
});
